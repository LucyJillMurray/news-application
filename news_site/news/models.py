"""
Database models for the news application.

These classes define the database tables for the news site. Reader,
Journalist and Editor each extend Django's built-in User with a one-to-one
link, and the remaining models capture the catalogue

"""

from django.db import models
from django.db.models import Q
from django.contrib.auth.models import User


class Publisher(models.Model):
    """This publisher class is used to link editors to a publisher.
    Every editor must belong to a publisher.

    Publishers can also log in like every other role, through a linked
    :class:`~django.contrib.auth.models.User`.

    :param str title: The title of the publisher (must be unique)
    :param str description: A short description of what the publisher does
    :param user: The Django User account this publisher logs in with, if any
    :type user: django.contrib.auth.models.User or None
    """

    title = models.CharField(max_length=200, unique=True)
    description = models.CharField(max_length=500)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="publisher_profile",
    )

    def __str__(self):
        """Return the publisher's title.

        :returns: The title of the publisher
        :rtype: str
        """
        return self.title


class Editor(models.Model):
    """A editor who belongs to a publisher. Linked to a Django User account."""

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    publisher = models.ForeignKey(
        "Publisher",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="editors",
    )


class Journalist(models.Model):
    """A journalist who writes articles. Linked to a Django User account.
    :param user: The Django User account associated with this journalist
    :type user: django.contrib.auth.models.User

    """

    user = models.OneToOneField(User, on_delete=models.CASCADE)

    def __str__(self):
        """Return the journalist's username.

        :returns: The username of the journalist
        :rtype: str
        """
        return self.user.username


class Newsletter(models.Model):
    """A group of articles created by a journalist or publisher.

    Exactly one of ``publisher`` or ``journalist`` must be set
    (enforced by a CheckConstraint); a newsletter cannot belong
    to both or neither.

    :param publisher: The publisher this newsletter belongs to, if any
    :type publisher: Publisher or None
    :param journalist: The journalist this newsletter belongs to, if any
    :type journalist: Journalist or None
    :param articles: The articles included in this newsletter
    :type articles: QuerySet[Article]
    :param created_date: The date and time the newsletter was created
    :type created_date: datetime.datetime
    :param title: The title of the newsletter
    :type title: str
    """

    publisher = models.ForeignKey(
        "Publisher",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="newsletters",
    )
    journalist = models.ForeignKey(
        "Journalist",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="newsletters",
    )
    articles = models.ManyToManyField(
        "Article", related_name="newsletters", blank=True
    )

    created_date = models.DateTimeField(auto_now_add=True)
    title = models.CharField(max_length=200)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(publisher__isnull=False, journalist__isnull=True)
                    | Q(publisher__isnull=True, journalist__isnull=False)
                ),
                name="newsletter_exactly_one_target",
            ),
        ]

    def __str__(self):
        """Return the newsletter's title.

        :returns: The title of the newsletter
        :rtype: str
        """
        return self.title


class Article(models.Model):
    """A single article within a newsletter"""

    STATUS_CHOICES = [
        ("self-published", "Self Published"),
        ("request-publishing", "Request Publishing"),
        ("published", "Published"),
    ]

    author = models.ForeignKey(
        Journalist, on_delete=models.CASCADE, related_name="items"
    )
    publisher = models.ForeignKey(
        Publisher,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="articles",
    )

    created_date = models.DateTimeField(auto_now_add=True)
    title = models.CharField(max_length=200)
    content = models.TextField()
    approved_status = models.BooleanField(default=False)  # approved article?
    published_status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="self-published"
    )

    @property
    def publisher_display(self):
        """Return the publisher's name, or 'Self Published' if there
        is none."""
        if self.publisher:
            return self.publisher.title
        return "Self Published"

    def __str__(self):
        return f"Title #{self.title}"


class Subscription(models.Model):
    """A reader's subscription to either a publisher or a journalist."""

    reader = models.ForeignKey(
        "Reader", on_delete=models.CASCADE, related_name="subscriptions"
    )

    publisher = models.ForeignKey(
        "Publisher",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subscribers",
    )
    journalist = models.ForeignKey(
        "Journalist",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subscribers",
    )

    subscription_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(publisher__isnull=False, journalist__isnull=True)
                    | Q(publisher__isnull=True, journalist__isnull=False)
                ),
                name="subscription_exactly_one_target",
            ),
            models.UniqueConstraint(
                fields=["reader", "publisher"],
                name="unique_reader_publisher_sub",
            ),
            models.UniqueConstraint(
                fields=["reader", "journalist"],
                name="unique_reader_journalist_sub",
            ),
        ]

    def __str__(self):
        target = self.publisher or self.journalist
        return f"{self.reader} subscribed to {target}"


class Reader(models.Model):
    """A reader who views articles and subscribes.
    Linked to a Django User account."""

    user = models.OneToOneField(User, on_delete=models.CASCADE)

    def __str__(self):
        # Show the buyer by their username
        return self.user.username
