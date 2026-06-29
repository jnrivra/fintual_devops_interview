from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import F
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.pagination import PageNumberPagination, paginate

from blog.models import Comment, Post, Tag, User
from blog.schemas import (
    CommentCreateIn,
    CommentCreateOut,
    PostCreateIn,
    PostCreateOut,
    PostDetailOut,
    PostListOut,
    UserDetailOut,
)

router = Router()


def _author_dict(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
    }


def _tag_dict(tag: Tag) -> dict:
    return {"id": tag.id, "name": tag.name, "slug": tag.slug}


def _post_list_qs():
    """Base queryset for the feed: pulls author (JOIN) and tags (prefetch) in one go,
    eliminating the N+1. django-ninja serializes the Schemas straight from the ORM."""
    return Post.objects.select_related("author").prefetch_related("tags")


@router.get("/posts", response=list[PostListOut])
@paginate(PageNumberPagination)
def list_posts(request):
    return _post_list_qs().filter(is_published=True).order_by("-created_at")


@router.get("/posts/search", response=list[PostListOut])
@paginate(PageNumberPagination)
def search_posts(request, q: str):
    # Full-text search over the GIN index (websearch: supports quotes and -negation).
    # Replaces the icontains that did a sequential scan over 100k rows.
    query = SearchQuery(q, search_type="websearch")
    return (
        _post_list_qs()
        .filter(search_vector=query, is_published=True)
        .annotate(rank=SearchRank("search_vector", query))
        .order_by("-rank", "-created_at")
    )


@router.get("/posts/by-tag/{slug}", response=list[PostListOut])
@paginate(PageNumberPagination)
def posts_by_tag(request, slug: str):
    tag = get_object_or_404(Tag, slug=slug)
    return _post_list_qs().filter(tags=tag, is_published=True).order_by("-created_at")


@router.get("/posts/{post_id}", response=PostDetailOut)
def get_post(request, post_id: int):
    post = get_object_or_404(
        Post.objects.select_related("author").prefetch_related("tags"), id=post_id
    )
    # Atomic increment in the DB: a single query, no race condition / lost update
    # (it used to be read-modify-write with post.save() rewriting the whole row).
    Post.objects.filter(id=post_id).update(view_count=F("view_count") + 1)

    # select_related on the comment authors: avoids the N+1 in the detail view.
    comments = [
        {
            "id": c.id,
            "author": _author_dict(c.author),
            "body": c.body,
            "created_at": c.created_at,
        }
        for c in post.comments.select_related("author").order_by("created_at")
    ]
    return {
        "id": post.id,
        "title": post.title,
        "body": post.body,
        "author": _author_dict(post.author),
        "tags": [_tag_dict(t) for t in post.tags.all()],
        "comments": comments,
        "view_count": post.view_count + 1,  # reflects the increment without re-reading the row
        "created_at": post.created_at,
        "updated_at": post.updated_at,
    }


@router.post("/posts", response=PostCreateOut)
def create_post(request, payload: PostCreateIn):
    author = get_object_or_404(User, id=payload.author_id)
    post = Post.objects.create(
        author=author,
        title=payload.title,
        body=payload.body,
    )
    if payload.tag_slugs:
        # One query to resolve all the tags instead of one per slug.
        tags = Tag.objects.filter(slug__in=payload.tag_slugs)
        post.tags.add(*tags)
    return {"id": post.id, "title": post.title}


@router.post("/posts/{post_id}/comments", response=CommentCreateOut)
def create_comment(request, post_id: int, payload: CommentCreateIn):
    post = get_object_or_404(Post, id=post_id)
    author = get_object_or_404(User, id=payload.author_id)
    comment = Comment.objects.create(post=post, author=author, body=payload.body)
    return {"id": comment.id}


@router.get("/users/find", response=UserDetailOut)
def find_user_by_email(request, email: str):
    user = get_object_or_404(User, email=email)
    return _user_detail(user)


@router.get("/users/{user_id}", response=UserDetailOut)
def get_user(request, user_id: int):
    user = get_object_or_404(User, id=user_id)
    return _user_detail(user)


def _user_detail(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "bio": user.bio,
        "post_count": user.posts.count(),
        "comment_count": user.comments.count(),
    }
