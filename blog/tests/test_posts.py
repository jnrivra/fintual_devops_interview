import pytest
from django.test import Client

from blog.models import Post, Tag, User


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def user(db):
    return User.objects.create(
        username="alice",
        email="alice@example.com",
        display_name="Alice",
    )


@pytest.mark.django_db
def test_list_posts_returns_published(client, user):
    tag = Tag.objects.create(name="Python", slug="python")
    post = Post.objects.create(author=user, title="Hello", body="World")
    post.tags.add(tag)
    Post.objects.create(author=user, title="Draft", body="...", is_published=False)

    response = client.get("/api/posts")

    assert response.status_code == 200
    data = response.json()
    # El feed ahora viene paginado: {"items": [...], "count": N}
    assert "items" in data and "count" in data
    titles = [p["title"] for p in data["items"]]
    assert "Hello" in titles
    assert "Draft" not in titles


@pytest.mark.django_db
def test_list_posts_constant_queries_no_n_plus_one(client, user):
    """El feed debe usar un número de queries CONSTANTE sin importar cuántos
    posts/autores/tags haya. Blinda el fix de N+1 contra regresiones."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    tag = Tag.objects.create(name="Python", slug="python")
    for i in range(10):
        u = User.objects.create(
            username=f"u{i}", email=f"u{i}@example.com", display_name=f"U{i}"
        )
        p = Post.objects.create(author=u, title=f"Post {i}", body="body")
        p.tags.add(tag)

    with CaptureQueriesContext(connection) as ctx:
        response = client.get("/api/posts")
    assert response.status_code == 200
    # count + posts(+author join) + tags prefetch = pocas queries, NO ~2N.
    assert len(ctx.captured_queries) <= 5, f"posible N+1: {len(ctx.captured_queries)} queries"


@pytest.mark.django_db
def test_search_uses_full_text(client, user):
    """La búsqueda full-text encuentra por contenido y excluye lo no relacionado."""
    Post.objects.create(author=user, title="Guía de PostgreSQL", body="índices y tsvector")
    Post.objects.create(author=user, title="Receta de cocina", body="tomate y albahaca")

    data = client.get("/api/posts/search?q=postgresql").json()
    titles = [p["title"] for p in data["items"]]
    assert "Guía de PostgreSQL" in titles
    assert "Receta de cocina" not in titles


@pytest.mark.django_db
def test_get_post_returns_detail(client, user):
    post = Post.objects.create(author=user, title="Hello", body="World")

    response = client.get(f"/api/posts/{post.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Hello"
    assert data["author"]["username"] == "alice"
    assert data["comments"] == []
