"""
Forms for the news application.

PublisherForm collects the details needed to register a publishing house
(along with its login account), and ArticleForm is a ModelForm used to
create and edit articles. The other pages (reader/journalist/editor
registration and newsletters) are handled directly in the views.
"""

from django import forms
from django.contrib.auth.models import User

from .models import Article, Publisher


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
        fields = ["title", "content", "publisher"]

    def __init__(self, *args, journalist=None, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = True
        # publisher is optional: blank means "independent"
        self.fields["publisher"].required = False
        self.fields["publisher"].empty_label = "Independent (no publisher)"
        if journalist is not None:
            self.fields["publisher"].queryset = journalist.publishers.filter(
                editors__isnull=False
            ).distinct()
        else:
            self.fields["publisher"].queryset = Publisher.objects.none()
