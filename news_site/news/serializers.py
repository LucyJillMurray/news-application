from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Article, Newsletter, Publisher


# Serializer for Django's built-in User model. Used when creating or
# representing the account behind a Reader, Journalist or Editor
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        # The model this serializer is based on
        model = User
        # Fields exposed through the API
        fields = [
            "id",  # User primary key (read-only by default)
            "username",  # Login name
            "email",  # Contact email
            "first_name",  # Given name
            "last_name",  # Family name
            "password",  # Write-only, see extra_kwargs below
        ]
        # The password should never be sent back out in API responses
        extra_kwargs = {
            "password": {"write_only": True},
        }

    def create(self, validated_data):
        """Create a new User, hashing the password before saving."""
        # Pop the password so we can hash it instead of storing plain text
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        if password is not None:
            # set_password hashes the value before saving
            user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        # Handle password separately so it stays hashed on update
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password is not None:
            instance.set_password(password)
        instance.save()
        return instance


# Serializer for the Publisher model (handles validation and representation
# of publisher data)
class PublisherSerializer(serializers.ModelSerializer):
    class Meta:
        # The model this serializer is based on
        model = Publisher
        # Fields exposed through the API
        fields = [
            "id",  # Publisher primary key
            "title",  # Publisher name
            "description",  # Short description of the publisher
        ]


# Serializer for the Article model (handles article creation, updates,
# and output)
class ArticleSerializer(serializers.ModelSerializer):
    class Meta:
        # The model this serializer is based on
        model = Article
        # Fields exposed through the API
        fields = [
            "id",  # Article primary key
            "author",  # Journalist who wrote it (read-only, see below)
            "publisher",  # Publisher it belongs to, or null if self-published
            "created_date",  # When the article was created (read-only)
            "title",  # Article headline
            "content",  # Body text
            "approved_status",  # Whether an editor approved it (read-only)
            "published_status",  # self-published/request-publishing/published
            "publisher_display",  # Convenience name, "Self Published" if none
        ]
        # 'author' is taken from the logged-in user, 'created_date' is set
        # automatically, and 'approved_status' is controlled by an editor;
        # so clients cannot set any of these directly
        read_only_fields = [
            "author",
            "created_date",
            "approved_status",
            "publisher_display",
        ]


# Serializer for the Newsletter model (a group of articles tied to
# a publisher or a journalist
class NewsletterSerializer(serializers.ModelSerializer):
    class Meta:
        # The model this serializer is based on
        model = Newsletter
        # Fields exposed through the API
        fields = [
            "id",  # Newsletter primary key
            "publisher",  # Owning publisher (or null)
            "journalist",  # Owning journalist (or null)
            "articles",  # Many-to-many set of articles included
            "created_date",  # When it was created (read-only)
            "title",  # Newsletter title
        ]
        # 'created_date' is set automatically by the model
        read_only_fields = ["created_date"]
