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
    # The feed is now paginated: {"items": [...], "count": N}
    assert "items" in data and "count" in data
    titles = [p["title"] for p in data["items"]]
    assert "Hello" in titles
    assert "Draft" not in titles


@pytest.mark.django_db
def test_list_posts_constant_queries_no_n_plus_one(client, user):
    """The feed must use a CONSTANT number of queries no matter how many
    posts/authors/tags there are. Guards the N+1 fix against regressions."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    tag = Tag.objects.create(name="Python", slug="python")
    for i in range(10):
        u = User.objects.create(username=f"u{i}", email=f"u{i}@example.com", display_name=f"U{i}")
        p = Post.objects.create(author=u, title=f"Post {i}", body="body")
        p.tags.add(tag)

    with CaptureQueriesContext(connection) as ctx:
        response = client.get("/api/posts")
    assert response.status_code == 200
    # count + posts(+author join) + tags prefetch = few queries, NOT ~2N.
    assert len(ctx.captured_queries) <= 5, f"possible N+1: {len(ctx.captured_queries)} queries"


@pytest.mark.django_db
def test_search_uses_full_text(client, user):
    """Full-text search finds posts by content and excludes unrelated ones."""
    Post.objects.create(author=user, title="PostgreSQL guide", body="indexes and tsvector")
    Post.objects.create(author=user, title="Cooking recipe", body="tomato and basil")

    data = client.get("/api/posts/search?q=postgresql").json()
    titles = [p["title"] for p in data["items"]]
    assert "PostgreSQL guide" in titles
    assert "Cooking recipe" not in titles


@pytest.mark.django_db
def test_get_post_returns_detail(client, user):
    post = Post.objects.create(author=user, title="Hello", body="World")

    response = client.get(f"/api/posts/{post.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Hello"
    assert data["author"]["username"] == "alice"
    assert data["comments"] == []
