"""
Automated tests for the News REST API and related role-based logic.

Run with:    python manage.py test news

All endpoints are referenced through reverse() using the url names from
news/urls.py, so there are no hard-coded paths to keep in sync.

NOTE ON THE DATABASE: the capstone uses MariaDB/MySQL. Django builds a
throwaway test database, so the DB_USER in your .env needs CREATE and DROP
privileges or `manage.py test` will fail during setup.
"""

from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User, Permission

from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework.authtoken.models import Token

from news.models import (
    Reader,
    Journalist,
    Editor,
    Publisher,
    Article,
    Newsletter,
    Subscription,
)

PASSWORD = "testpass123"


# ---------------------------------------------------------------------------
# Helpers for building users with roles and related objects
# ---------------------------------------------------------------------------
def make_user(username):
    """Create a Django auth user with a known password and a real email."""
    return User.objects.create_user(
        username=username,
        password=PASSWORD,
        email=f"{username}@example.com",
        first_name=username.title(),
        last_name="Test",
    )


def make_reader(username="reader1"):
    user = make_user(username)
    return user, Reader.objects.create(user=user)


def make_journalist(username="journo1"):
    user = make_user(username)
    return user, Journalist.objects.create(user=user)


def make_publisher(title="Pub", description="A publisher"):
    return Publisher.objects.create(title=title, description=description)


def make_editor(username="editor1", publisher=None):
    user = make_user(username)
    if publisher is None:
        publisher = make_publisher(title=f"{username}-pub")
    return user, Editor.objects.create(user=user, publisher=publisher)


def grant(user, codename):
    """Give a user a news-app model permission by codename."""
    perm = Permission.objects.get(
        codename=codename, content_type__app_label="news"
    )
    user.user_permissions.add(perm)


def make_article(
    author,
    publisher=None,
    approved=False,
    published_status="self-published",
    title="An article",
):
    return Article.objects.create(
        author=author,
        publisher=publisher,
        title=title,
        content="Some body text.",
        approved_status=approved,
        published_status=published_status,
    )


# ===========================================================================
# 1. Authenticated access per role
# ===========================================================================
class AuthenticationAccessTests(APITestCase):
    """Endpoints require authentication; write endpoints require a role."""

    def setUp(self):
        self.reader_user, self.reader = make_reader()
        self.journo_user, self.journalist = make_journalist()
        self.approved_url = reverse("news:api_articles")
        self.create_url = reverse("news:api_articles")

    def test_unauthenticated_request_is_rejected(self):
        # No credentials -> DRF returns 401 (TokenAuthentication) or 403
        response = self.client.get(self.approved_url)
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_authenticated_user_can_read_approved(self):
        # Any logged-in user may read the approved list (success case)
        self.client.force_authenticate(user=self.reader_user)
        response = self.client.get(self.approved_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_reader_cannot_create_article(self):
        # Authenticated, but no Journalist profile -> 403 (failed case)
        self.client.force_authenticate(user=self.reader_user)
        response = self.client.post(
            self.create_url,
            {
                "title": "x",
                "content": "y",
                "published_status": "self-published",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# ===========================================================================
# 2. Reader can only retrieve their subscribed content
# ===========================================================================
class ReaderSubscriptionAPITests(APITestCase):

    def setUp(self):
        self.reader_user, self.reader = make_reader()
        _, self.journalist = make_journalist("journo_sub")

        self.pub_a = make_publisher(title="Pub A")
        self.pub_b = make_publisher(title="Pub B")

        # Approved article under each publisher
        self.article_a = make_article(
            self.journalist,
            publisher=self.pub_a,
            approved=True,
            published_status="published",
            title="From A",
        )
        self.article_b = make_article(
            self.journalist,
            publisher=self.pub_b,
            approved=True,
            published_status="published",
            title="From B",
        )

        self.url = reverse("news:api_view_subscribed")
        self.client.force_authenticate(user=self.reader_user)

    def test_reader_sees_only_subscribed_publisher_articles(self):
        Subscription.objects.create(reader=self.reader, publisher=self.pub_a)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        titles = [a["title"] for a in response.json()]
        self.assertIn("From A", titles)  # subscribed content shown
        self.assertNotIn("From B", titles)  # unsubscribed excluded

    def test_reader_with_no_subscriptions_sees_nothing(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), [])

    def test_subscribing_to_journalist_returns_their_articles(self):
        Subscription.objects.create(
            reader=self.reader, journalist=self.journalist
        )
        response = self.client.get(self.url)
        titles = [a["title"] for a in response.json()]
        # Both articles are by this journalist, so both appear
        self.assertIn("From A", titles)
        self.assertIn("From B", titles)

    def test_unapproved_articles_are_never_returned(self):
        # Subscribed, but the article is not approved -> excluded
        Subscription.objects.create(reader=self.reader, publisher=self.pub_a)
        make_article(
            self.journalist,
            publisher=self.pub_a,
            approved=False,
            title="Pending",
        )
        response = self.client.get(self.url)
        titles = [a["title"] for a in response.json()]
        self.assertNotIn("Pending", titles)

    def test_non_reader_gets_403_on_subscribed(self):
        journo_user, _ = make_journalist("journo_only")
        self.client.force_authenticate(user=journo_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# ===========================================================================
# 3. Journalist can create articles
# ===========================================================================
class JournalistCreateAPITests(APITestCase):

    def setUp(self):
        self.journo_user, self.journalist = make_journalist()
        self.url = reverse("news:api_articles")
        self.client.force_authenticate(user=self.journo_user)

    def test_journalist_creates_article_success(self):
        payload = {
            "title": "My first API article",
            "content": "This is the body.",
            "published_status": "self-published",
        }
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        article = Article.objects.get(title="My first API article")
        self.assertEqual(article.author, self.journalist)
        self.assertFalse(article.approved_status)  # starts unapproved

    def test_create_with_missing_title_returns_field_error(self):
        # The explicit-validation behaviour: missing required field -> 400
        response = self.client.post(
            self.url, {"content": "Body with no title."}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("title", response.json())

    def test_create_cannot_self_approve(self):
        # approved_status is read-only; a client value must be ignored
        payload = {
            "title": "Sneaky",
            "content": "trying to self-approve",
            "published_status": "self-published",
            "approved_status": True,
        }
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(Article.objects.get(title="Sneaky").approved_status)


# ===========================================================================
# 4. Single-article retrieval respects approval
# ===========================================================================
class SingleArticleAPITests(APITestCase):

    def setUp(self):
        self.reader_user, _ = make_reader()
        _, self.journalist = make_journalist("journo_single")
        self.client.force_authenticate(user=self.reader_user)

    def test_approved_article_is_returned(self):
        article = make_article(self.journalist, approved=True)
        url = reverse("news:api_article_detail", args=[article.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["id"], article.id)

    def test_unapproved_article_is_hidden(self):
        # Matches your Postman result: "No Article matches the given query."
        article = make_article(self.journalist, approved=False)
        url = reverse("news:api_article_detail", args=[article.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# ===========================================================================
# 5. Journalist update / delete ownership rules
# ===========================================================================
class JournalistUpdateDeleteAPITests(APITestCase):

    def setUp(self):
        self.owner_user, self.owner = make_journalist("owner")
        self.other_user, self.other = make_journalist("intruder")
        self.article = make_article(self.owner, approved=True, title="Owned")

    def test_owner_can_update_and_it_unapproves(self):
        self.client.force_authenticate(user=self.owner_user)
        url = reverse("news:api_article_detail", args=[self.article.id])
        response = self.client.put(
            url, {"title": "Edited title"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.article.refresh_from_db()
        self.assertEqual(self.article.title, "Edited title")
        self.assertFalse(self.article.approved_status)  # editing un-approves

    def test_non_owner_cannot_update(self):
        self.client.force_authenticate(user=self.other_user)
        url = reverse("news:api_article_detail", args=[self.article.id])
        response = self.client.put(url, {"title": "Hacked"}, format="json")
        # author scoping hides other journalists' articles
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_owner_can_delete(self):
        self.client.force_authenticate(user=self.owner_user)
        url = reverse("news:api_article_detail", args=[self.article.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Article.objects.filter(id=self.article.id).exists())

    def test_non_journalist_cannot_delete(self):
        reader_user, _ = make_reader("reader_del")
        self.client.force_authenticate(user=reader_user)
        url = reverse("news:api_article_detail", args=[self.article.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# ===========================================================================
# 6. Editor can approve and delete  (HTML views -> Django test Client)
# ===========================================================================
class EditorApprovalTests(TestCase):

    def setUp(self):
        self.publisher = make_publisher(title="Editor Pub")
        self.editor_user, self.editor = make_editor(
            "editor_approve", publisher=self.publisher
        )
        _, self.journalist = make_journalist("journo_for_editor")
        self.article = make_article(
            self.journalist,
            publisher=self.publisher,
            approved=False,
            published_status="request-publishing",
        )
        self.url = reverse("news:set_article_approval", args=[self.article.id])
        self.client.login(username="editor_approve", password=PASSWORD)

    def test_editor_can_approve_article(self):
        response = self.client.post(self.url, {"approve": "true"})
        self.assertEqual(response.status_code, 302)  # redirect on success
        self.article.refresh_from_db()
        self.assertTrue(self.article.approved_status)

    def test_editor_can_unapprove_article(self):
        self.article.approved_status = True
        self.article.save()
        self.client.post(self.url, {"approve": "false"})
        self.article.refresh_from_db()
        self.assertFalse(self.article.approved_status)

    def test_non_editor_is_forbidden(self):
        self.client.logout()
        make_reader("plain_reader")
        self.client.login(username="plain_reader", password=PASSWORD)
        response = self.client.post(self.url, {"approve": "true"})
        self.assertEqual(response.status_code, 403)  # editor_required blocks
        self.article.refresh_from_db()
        self.assertFalse(self.article.approved_status)  # unchanged


class EditorDeleteNewsletterTests(TestCase):
    """Editors delete via the newsletter delete view (they hold the
    delete_newsletter permission in your registration flow)."""

    def setUp(self):
        self.publisher = make_publisher(title="Del Pub")
        self.editor_user, self.editor = make_editor(
            "editor_delete", publisher=self.publisher
        )
        grant(self.editor_user, "delete_newsletter")
        self.newsletter = Newsletter.objects.create(
            title="To delete", publisher=self.publisher
        )
        self.url = reverse("news:delete_newsletter", args=[self.newsletter.id])
        self.client.login(username="editor_delete", password=PASSWORD)

    def test_editor_with_permission_can_delete_newsletter(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            Newsletter.objects.filter(id=self.newsletter.id).exists()
        )

    def test_editor_without_permission_cannot_delete(self):
        self.editor_user.user_permissions.clear()
        # Re-login so the permission cache is rebuilt for the next request
        self.client.logout()
        self.client.login(username="editor_delete", password=PASSWORD)
        self.client.post(self.url)
        self.assertTrue(
            Newsletter.objects.filter(id=self.newsletter.id).exists()
        )


# ===========================================================================
# 7. Newsletters behave correctly + email mocking
# ===========================================================================
class NewsletterEmailTests(TestCase):
    """email_newsletter sends to every subscriber of the owning journalist
    or publisher. send_mail is mocked so no real email is attempted."""

    def setUp(self):
        self.journo_user, self.journalist = make_journalist("journo_news")
        self.newsletter = Newsletter.objects.create(
            title="Weekly Roundup", journalist=self.journalist
        )
        self.reader_user, self.reader = make_reader("subscriber1")
        Subscription.objects.create(
            reader=self.reader, journalist=self.journalist
        )
        self.url = reverse("news:email_newsletter", args=[self.newsletter.id])
        self.client.login(username="journo_news", password=PASSWORD)

    @patch("news.views.send_mail")
    def test_email_sent_to_subscribers(self, mock_send_mail):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(mock_send_mail.called)  # success: email fired

        _, kwargs = mock_send_mail.call_args
        recipients = kwargs.get("recipient_list", [])
        self.assertIn("subscriber1@example.com", recipients)

    @patch("news.views.send_mail")
    def test_no_email_when_no_subscribers(self, mock_send_mail):
        Subscription.objects.all().delete()  # remove the only subscriber
        empty = Newsletter.objects.create(
            title="No readers", journalist=self.journalist
        )
        url = reverse("news:email_newsletter", args=[empty.id])
        self.client.post(url)
        self.assertFalse(mock_send_mail.called)  # nothing to send

    @patch("news.views.send_mail")
    def test_get_request_does_not_send(self, mock_send_mail):
        # The view only acts on POST, to avoid accidental sends
        self.client.get(self.url)
        self.assertFalse(mock_send_mail.called)


# ===========================================================================
# 8. /api/articles/ approved-list integration
#    (the rubric's "alternative logic" / external-share simulation)
# ===========================================================================
class ApprovedArticlesIntegrationTests(APITestCase):
    """Only approved articles surface through the public list endpoint,
    regardless of author."""

    def setUp(self):
        self.viewer_user, _ = make_reader("viewer")
        _, self.journalist = make_journalist("journo_int")
        make_article(self.journalist, approved=True, title="Visible")
        make_article(self.journalist, approved=False, title="Hidden")
        self.url = reverse("news:api_articles")
        self.client.force_authenticate(user=self.viewer_user)

    def test_only_approved_articles_are_listed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [a["title"] for a in response.json()]
        self.assertIn("Visible", titles)
        self.assertNotIn("Hidden", titles)


# ===========================================================================
# 9. Approval side-effects (Option 2: email subscribers + self-POST)
#    Both send_mail and requests.post are mocked, so no real email is sent
#    and no second server needs to be running during the test.
# ===========================================================================
class ApprovalSideEffectTests(TestCase):

    def setUp(self):
        self.publisher = make_publisher(title="Notify Pub")
        self.editor_user, self.editor = make_editor(
            "editor_notify", publisher=self.publisher
        )
        _, self.journalist = make_journalist("journo_notify")

        # A reader subscribed to the journalist who wrote the article
        self.reader_user, self.reader = make_reader("notify_sub")
        Subscription.objects.create(
            reader=self.reader, journalist=self.journalist
        )

        self.article = make_article(
            self.journalist,
            publisher=self.publisher,
            approved=False,
            published_status="request-publishing",
            title="Big scoop",
        )

        self.url = reverse("news:set_article_approval", args=[self.article.id])
        self.client.login(username="editor_notify", password=PASSWORD)

    @patch("news.views.requests.post")
    @patch("news.views.send_mail")
    def test_approval_emails_subscribers_and_posts_to_api(
        self, mock_send_mail, mock_post
    ):
        response = self.client.post(self.url, {"approve": "true"})
        self.assertEqual(response.status_code, 302)

        self.article.refresh_from_db()
        self.assertTrue(self.article.approved_status)

        # Email went out to the subscriber (success case)
        self.assertTrue(mock_send_mail.called)
        _, kwargs = mock_send_mail.call_args
        self.assertIn(
            "notify_sub@example.com", kwargs.get("recipient_list", [])
        )

        # The approved article was POSTed to our own /api/approved/ endpoint
        self.assertTrue(mock_post.called)

    @patch("news.views.requests.post")
    @patch("news.views.send_mail")
    def test_unapprove_does_not_trigger_side_effects(
        self, mock_send_mail, mock_post
    ):
        # Setting approve=false must NOT email or POST (failed/negative case)
        self.client.post(self.url, {"approve": "false"})
        self.assertFalse(mock_send_mail.called)
        self.assertFalse(mock_post.called)


# ===========================================================================
# 10. Token-based authentication
#     The /api/token/ endpoint issues a token, and that token authenticates
#     subsequent API requests (the scheme required by the brief).
# ===========================================================================
class TokenAuthTests(APITestCase):

    def setUp(self):
        self.reader_user, _ = make_reader("token_reader")
        self.token_url = reverse("news:api_token")
        self.articles_url = reverse("news:api_articles")

    def test_valid_credentials_return_a_token(self):
        # Success case: correct username/password yields a token
        response = self.client.post(
            self.token_url,
            {"username": "token_reader", "password": PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("token", response.json())

    def test_invalid_credentials_are_rejected(self):
        # Failed case: wrong password returns 400, no token issued
        response = self.client.post(
            self.token_url,
            {"username": "token_reader", "password": "wrong"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_token_authenticates_api_request(self):
        # A real token in the Authorization header authenticates the request
        token = Token.objects.create(user=self.reader_user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)
        response = self.client.get(self.articles_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_request_without_token_is_rejected(self):
        # No credentials at all -> not authenticated
        response = self.client.get(self.articles_url)
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )
