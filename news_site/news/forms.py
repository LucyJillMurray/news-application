"""
Forms for the news application.

These forms back the registration, article and newsletter pages. The
registration forms build a Django User plus the matching role record
(Reader, Journalist or Editor), while ArticleForm and NewsletterForm are
ModelForms tied directly to their models.
"""

from django import forms
from django.contrib.auth.models import User

from .models import Article, Newsletter, Publisher


class ReaderRegistrationForm(forms.Form):
    """Collect the details needed to create a new reader account.

    :param str first_name: The reader's first name
    :param str last_name: The reader's last name
    :param str username: The desired username; must not already be taken
    :param str email: The reader's email address
    :param str password: The reader's chosen password
    """

    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    username = forms.CharField(max_length=150)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)

    def clean_username(self):
        """Reject usernames that are already taken.

        :returns: The cleaned username, if it isn't already in use
        :rtype: str
        :raises django.forms.ValidationError: If the username is already
            taken
        """
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Username already taken")
        return username


class JournalistRegistrationForm(ReaderRegistrationForm):
    """Same fields as a reader; used to create a journalist account."""


class EditorRegistrationForm(ReaderRegistrationForm):
    """Reader fields plus the publisher the editor belongs to."""

    publisher = forms.ModelChoiceField(
        queryset=Publisher.objects.all(),
        empty_label="Select a publisher",
    )


class PublisherForm(forms.ModelForm):
    """Create a publisher record together with its login account.

    :param str username: The username the publisher will log in with;
        must not already be taken
    :param str password: The publisher's chosen password (min 8 chars)
    :param str password_confirm: Repeat of the password; must match
    """

    username = forms.CharField(max_length=150, label="Username")
    password = forms.CharField(
        widget=forms.PasswordInput, min_length=8, label="Password"
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput, label="Confirm Password"
    )

    class Meta:
        model = Publisher
        fields = ["title", "description"]

    def clean_title(self):
        # Publisher titles must be unique.
        title = self.cleaned_data["title"]
        if Publisher.objects.filter(title=title).exists():
            raise forms.ValidationError("Title already taken")
        return title

    def clean_username(self):
        # Login usernames must be unique across all User accounts.
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Username already taken")
        return username

    def clean(self):
        # The two password fields must match.
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")
        if password and password_confirm and password != password_confirm:
            self.add_error("password_confirm", "Passwords do not match")
        return cleaned_data


class ArticleForm(forms.ModelForm):
    """Create or edit an article."""

    class Meta:
        model = Article
        fields = [
            "title",
            "content",
            "published_status",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = True

        # Journalists can request publishing or self-publish, but cannot
        # set an article straight to "Published" themselves.
        self.fields["published_status"].choices = [
            ("self-published", "Self Published"),
            ("request-publishing", "Request Publishing"),
        ]

    def clean_published_status(self):
        # Enforce the restriction even if someone POSTs "published" directly.
        status = self.cleaned_data["published_status"]
        allowed = {"self-published", "request-publishing"}
        if status not in allowed:
            raise forms.ValidationError(
                "You cannot publish this article directly."
            )
        return status


class NewsletterForm(forms.ModelForm):
    """Create or edit a newsletter.

    The ``articles`` queryset is normally narrowed by the view to the
    articles the logged-in journalist or editor is allowed to include.
    """

    class Meta:
        model = Newsletter
        fields = ["title", "articles"]

    def clean_articles(self):
        # A newsletter must contain at least one article.
        articles = self.cleaned_data.get("articles")
        if not articles:
            raise forms.ValidationError("At least one article required")
        return articles
