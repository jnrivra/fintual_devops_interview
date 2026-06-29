from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.db import models
from django.utils import timezone


class User(models.Model):
    username = models.CharField(max_length=64, unique=True)
    # email se consulta en /api/users/find: debe ser único (evita perfiles
    # duplicados) y va indexado por el unique constraint.
    email = models.EmailField(max_length=255, unique=True)
    display_name = models.CharField(max_length=128)
    bio = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self) -> str:
        return self.username


class Tag(models.Model):
    name = models.CharField(max_length=64, unique=True)
    slug = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self) -> str:
        return self.name


class Post(models.Model):
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="posts")
    title = models.CharField(max_length=255)
    body = models.TextField()
    is_published = models.BooleanField(default=True)
    view_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    tags = models.ManyToManyField(Tag, related_name="posts", blank=True)
    # Columna tsvector mantenida por Postgres (GENERATED ALWAYS ... STORED).
    # GeneratedField le dice a Django que la DB la calcula sola: nunca la escribe
    # en INSERT/UPDATE y queda siempre en sync. Indexada con GIN (ver Meta).
    search_vector = models.GeneratedField(
        expression=SearchVector("title", "body", config="english"),
        output_field=SearchVectorField(),
        db_persist=True,
    )

    class Meta:
        indexes = [
            # El feed filtra is_published y ordena por -created_at: un índice
            # compuesto cubre ambos y elimina el sort en disco.
            models.Index(fields=["is_published", "-created_at"], name="post_pub_created_idx"),
            # GIN sobre el tsvector: búsqueda de texto sin sequential scan.
            GinIndex(fields=["search_vector"], name="post_search_gin"),
        ]

    def __str__(self) -> str:
        return self.title


class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="comments")
    body = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            # El detalle de un post ordena sus comentarios por created_at.
            models.Index(fields=["post", "created_at"], name="comment_post_created_idx"),
        ]
