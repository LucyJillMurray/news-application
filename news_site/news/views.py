from functools import wraps
import requests
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db.models import Q
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import (
    User,
    Group,
    Permission,
)  # Django's built-in user, group, and permission models
from .models import (
    Reader,
    Editor,
    Journalist,
    Publisher,
    Newsletter,
    Article,
    Subscription,
)
from .forms import PublisherForm
from django.urls import reverse
from django.http import (
    HttpResponseRedirect,
    HttpResponseForbidden,
)  # For sending a 403 response
from django.contrib.auth import (
    authenticate,
    login,
    logout,
)  # Functions to handle login
from django import forms
from datetime import timedelta
from django.utils import timezone
from django.core.mail import send_mail
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.conf import settings
from django.contrib import messages
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.authentication import BasicAuthentication
from rest_framework.response import Response
from rest_framework import status
from .serializers import ArticleSerializer


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------
def editor_required(view_func):
    """Allow access only to logged-in users who have an Editor profile.

    Unauthenticated users are redirected to login (via login_required);
    authenticated users without an Editor record get a 403.
    """

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not Editor.objects.filter(user=request.user).exists():
            return HttpResponseForbidden("Editors only")
        return view_func(request, *args, **kwargs)

    return login_required(_wrapped)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
# Logs the user out and redirects to login page
def logout_user(request):
    """Log the current user out and send them back to the login page."""
    logout(request)
    return redirect("news:login")


def register_reader(request):
    """Register a new reader account and log them straight in.

    On GET, shows the empty registration form. On POST, creates a User and a
    linked Reader record, adds the user to the "Readers" group, grants the
    "delete_subscription" permission, logs them in, and redirects to the
    reader home page. If the requested username is already taken, no user
    is created and the form is re-rendered with an error message.

    :param request: The HTTP request. On POST, expects "first_name",
        "last_name", "username", "password", and "email" in request.POST.
    :type request: django.http.HttpRequest

    :returns: A rendered registration form (GET, or POST with a taken
        username), or a redirect to the reader home page (POST success)
    :rtype: django.http.HttpResponse or django.http.HttpResponseRedirect
    """
    if request.method == "POST":
        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        username = request.POST.get("username")
        password = request.POST.get("password")
        email = request.POST.get("email")

        if User.objects.filter(username=username).exists():
            return render(
                request,
                "news/register_reader.html",
                {"error": "Username already taken"},
            )
        else:
            user = User.objects.create_user(
                username=username,
                password=password,
                email=email,
                first_name=first_name,
                last_name=last_name,
            )

            Reader.objects.create(user=user)
            reader_group, _ = Group.objects.get_or_create(name="Readers")
            user.groups.add(reader_group)
            try:
                delete_subscription_perm = Permission.objects.get(
                    codename="delete_subscription",
                    content_type__app_label="news",
                )
                user.user_permissions.add(delete_subscription_perm)
            except Permission.DoesNotExist:
                pass

            user.save()

            login(request, user)

            return redirect(reverse("news:reader_home"))

    else:
        return render(request, "news/register_reader.html")


def register_journalist(request):
    """Register a new journalist account and log them straight in.

    On GET, shows the empty registration form. On POST, creates a User and a
    linked Journalist record, adds the user to the "Journalists" group, logs
    them in and sends them to the journalist home page.
    """
    if request.method == "POST":
        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        username = request.POST.get("username")
        password = request.POST.get("password")
        email = request.POST.get("email")

        if User.objects.filter(username=username).exists():
            return render(
                request,
                "news/register_journalist.html",
                {"error": "Username already taken"},
            )
        else:
            user = User.objects.create_user(
                username=username,
                password=password,
                email=email,
                first_name=first_name,
                last_name=last_name,
            )

            Journalist.objects.create(user=user)

            journalist_group, _ = Group.objects.get_or_create(
                name="Journalists"
            )
            user.groups.add(journalist_group)
            try:
                delete_newsletter_perm = Permission.objects.get(
                    codename="delete_newsletter",
                    content_type__app_label="news",
                )
                user.user_permissions.add(delete_newsletter_perm)
            except Permission.DoesNotExist:
                pass

            try:
                delete_article_perm = Permission.objects.get(
                    codename="delete_article",
                    content_type__app_label="news",
                )
                user.user_permissions.add(delete_article_perm)
            except Permission.DoesNotExist:
                pass
            user.save()

            login(request, user)

            return redirect(reverse("news:journalist_home"))

    else:
        return render(request, "news/register_journalist.html")


def register_publisher(request):
    """Self-service registration for a publishing house.

    On GET, shows the empty :class:`~news.forms.PublisherForm`. On POST,
    validates it, creates a linked :class:`~django.contrib.auth.models.User`
    plus the :class:`~news.models.Publisher` record, adds the user to the
    "Publishers" group, logs them in and sends them to the publisher home
    page.

    :param request: The HTTP request. On POST, expects the PublisherForm
        fields ("title", "description", "username", "password",
        "password_confirm") in request.POST.
    :type request: django.http.HttpRequest
    :returns: A rendered registration form (GET, or an invalid POST), or a
        redirect to the publisher home page (POST success)
    :rtype: django.http.HttpResponse or django.http.HttpResponseRedirect
    """
    if request.method == "POST":
        form = PublisherForm(request.POST)
        if form.is_valid():
            publisher = form.save(commit=False)

            user = User.objects.create_user(
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password"],
            )
            publisher.user = user
            publisher.save()

            publisher_group, _ = Group.objects.get_or_create(name="Publishers")
            user.groups.add(publisher_group)

            login(request, user)
            return redirect("news:publisher_home")
    else:
        form = PublisherForm()

    return render(request, "news/register_publisher.html", {"form": form})


def register_editor(request):
    """Register a new editor account and log them straight in.

    On GET, shows the empty registration form. On POST, creates a User and a
    linked Editor record (tied to a chosen publisher), adds the user to the
    "Editors" group, logs them in and sends them to the editor home page.
    """
    if request.method == "POST":
        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        username = request.POST.get("username")
        password = request.POST.get("password")
        email = request.POST.get("email")

        publisher_id = request.POST.get("publisher")
        publisher = Publisher.objects.filter(pk=publisher_id).first()
        publishers = Publisher.objects.all().order_by("title")

        if publisher is None:
            return render(
                request,
                "news/register_editor.html",
                {
                    "error": "Please select a valid publisher",
                    "publishers": publishers,
                },
            )

        if User.objects.filter(username=username).exists():
            return render(
                request,
                "news/register_editor.html",
                {"error": "Username already taken", "publishers": publishers},
            )

        else:
            user = User.objects.create_user(
                username=username,
                password=password,
                email=email,
                first_name=first_name,
                last_name=last_name,
            )
            Editor.objects.create(user=user, publisher=publisher)

            editor_group, _ = Group.objects.get_or_create(name="Editors")
            user.groups.add(editor_group)
            try:
                delete_newsletter_perm = Permission.objects.get(
                    codename="delete_newsletter",
                    content_type__app_label="news",
                )
                user.user_permissions.add(delete_newsletter_perm)
            except Permission.DoesNotExist:
                pass

            try:
                delete_article_perm = Permission.objects.get(
                    codename="delete_article",
                    content_type__app_label="news",
                )
                user.user_permissions.add(delete_article_perm)
            except Permission.DoesNotExist:
                pass
            user.save()

            login(request, user)

            return redirect(reverse("news:editor_home"))

    else:
        publishers = Publisher.objects.all().order_by("title")
        return render(
            request,
            "news/register_editor.html",
            {"publishers": publishers},
        )


# ---------------------------------------------------------------------------
# Home pages
# ---------------------------------------------------------------------------
def login_user(request):
    """Log a user in and send them to the correct home page for their role.

    On POST, checks the submitted username and password. If they are valid the
    user is logged in, the session is set to expire in one day, and the user is
    redirected based on their role: staff go to the publisher dashboard,
    editors to the editor home, journalists to the journalist home, and
    everyone else to the reader home. Invalid credentials re-show the login
    page with an error.
    """
    # When the login form is submitted
    if request.method == "POST":
        # Get username and password from the form
        username = request.POST.get("username")
        password = request.POST.get("password")

        # Check if the username and password match a user in the database
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)  # Log the user in and start their session

            # Set the session to expire on the next day
            now = timezone.now()
            exp_date = now + timedelta(days=1)
            expiry_seconds = int((exp_date - now).total_seconds())
            if expiry_seconds > 0:
                request.session.set_expiry(
                    expiry_seconds
                )  # Set the expiry time for the session

            # Save some user info in the session
            request.session["user_id"] = user.id
            request.session["username"] = user.username

            # Route based on the user's role
            if user.is_staff:  # admin
                return HttpResponseRedirect(reverse("news:admin_home"))
            elif Editor.objects.filter(user=user).exists():  # editor
                return HttpResponseRedirect(reverse("news:editor_home"))
            elif Journalist.objects.filter(user=user).exists():  # journalist
                return HttpResponseRedirect(reverse("news:journalist_home"))
            elif Publisher.objects.filter(user=user).exists():  # publisher
                return HttpResponseRedirect(reverse("news:publisher_home"))
            else:  # reader
                return HttpResponseRedirect(reverse("news:reader_home"))
        else:
            # If login failed, reload login page with an error message
            return render(
                request,
                "news/login.html",
                {"error": "Invalid credentials"},
            )
    else:
        # If the user just opened the login page, show the login form
        return render(request, "news/login.html")


@login_required
def reader_home(request):
    """Show the reader's home page with their list of current subscriptions."""
    reader = Reader.objects.filter(user=request.user).first()

    subscriptions = Subscription.objects.filter(reader=reader).order_by(
        "-subscription_date"
    )
    context = {
        "reader": reader,
        "subscriptions": subscriptions,
    }

    return render(request, "news/reader_home.html", context)


@login_required
def journalist_home(request):
    """Show the journalist's home page."""
    journalist = get_object_or_404(Journalist, user=request.user)

    return render(
        request,
        "news/journalist_home.html",
        {
            "journalist": journalist,
        },
    )


@login_required
def editor_home(request):
    """Show the editor home page."""
    editor = get_object_or_404(Editor, user=request.user)

    return render(request, "news/editor_home.html", {"editor": editor})


@login_required
def publisher_home(request):
    """Show the publisher's own home page.

    :param request: The HTTP request from the logged-in publisher
    :type request: django.http.HttpRequest
    :returns: The rendered publisher home page
    :rtype: django.http.HttpResponse
    """
    publisher = get_object_or_404(Publisher, user=request.user)
    return render(
        request, "news/publisher_home.html", {"publisher": publisher}
    )


def admin_home(request):
    """Show the admin dashboard listing all publishers and editors.

    The admin can remove either a publisher or an editor from here.
    """
    publishers = Publisher.objects.all().order_by("title")
    editors = Editor.objects.select_related("user", "publisher").order_by(
        "user__username"
    )
    return render(
        request,
        "news/admin_home.html",
        {"publishers": publishers, "editors": editors},
    )


@editor_required
def article_dashboard(request):
    """Show the article dashboard (editors only)."""
    return render(request, "news/article_dashboard.html")


# ---------------------------------------------------------------------------
# Articles (journalist)
# ---------------------------------------------------------------------------
@login_required
def article_directory(request):
    """List all of the articles created by the journalist."""
    journalist = get_object_or_404(Journalist, user=request.user)
    articles = Article.objects.filter(author=journalist).order_by(
        "-created_date"
    )

    context = {
        "journalist": journalist,
        "articles": articles,
    }
    return render(
        request,
        "news/article_directory.html",
        context,
    )


class ArticleForm(forms.ModelForm):
    """Create or edit an article."""

    # Declared explicitly so journalists can only pick these two.
    # "published" is deliberately excluded. (only editors publish)
    published_status = forms.ChoiceField(
        choices=[
            ("self-published", "Self Published"),
            ("request-publishing", "Request Publishing"),
        ]
    )

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


@login_required
def create_article(request):
    """Create a new article for the logged-in journalist (on POST)."""
    if request.method == "POST":
        journalist = get_object_or_404(Journalist, user=request.user)
        form = ArticleForm(request.POST, request.FILES)
        if form.is_valid():
            article = form.save(commit=False)
            article.author = journalist
            # Self-published articles have no publisher; they show as "Self".
            article.publisher = None
            # New articles always start unapproved (only an editor approves)
            article.approved_status = False
            article.save()
            return redirect("news:article_directory")
    else:
        form = ArticleForm()

    return render(request, "news/create_article.html", {"form": form})


@login_required
def delete_article(request, article_id):
    """Delete one of the journalist's articles, if they have the delete
    permission."""
    if not request.user.has_perm("news.delete_article"):
        return redirect("news:journalist_home")  # or show a 403 page

    journalist = get_object_or_404(Journalist, user=request.user)
    article = get_object_or_404(Article, id=article_id, author=journalist)

    if request.method == "POST":
        article.delete()
        return redirect("news:article_directory")
    else:
        return redirect("news:article_directory")


@login_required
def update_article(request, article_id):
    """Edit one of the journalist's own articles.
    The article must belong to the logged-in journalist. On GET the form is
    shown pre-filled; on POST the changes are saved and the journalist is
    returned to the article list.
    """
    journalist = get_object_or_404(Journalist, user=request.user)
    article = get_object_or_404(Article, id=article_id, author=journalist)

    if request.method == "POST":
        form = ArticleForm(request.POST, request.FILES, instance=article)
        if form.is_valid():
            form.save()
            article.approved_status = False  # editing un-approves the article
            article.published_status = (
                "request-publishing"  # force back to unpublished-equivalent
            )
            article.save()
            return redirect("news:article_directory")
    else:
        form = ArticleForm(instance=article)

    return render(
        request,
        "news/create_article.html",
        {"form": form, "article": article},
    )


# ---------------------------------------------------------------------------
# Newsletters (shared by editor + journalist)
# ---------------------------------------------------------------------------
@login_required
def newsletter_directory(request):
    """List all of the newsletters created by the journalist or editor."""
    journalist = Journalist.objects.filter(user=request.user).first()
    editor = Editor.objects.filter(user=request.user).first()
    if editor:
        newsletters = Newsletter.objects.filter(
            publisher=editor.publisher
        ).order_by("-created_date")
        context = {
            "publisher": editor.publisher,
            "newsletters": newsletters,
        }

    elif journalist:
        newsletters = Newsletter.objects.filter(
            journalist=journalist
        ).order_by("-created_date")
        context = {
            "journalist": journalist,
            "newsletters": newsletters,
        }

    else:
        return HttpResponseForbidden("Not allowed")

    return render(
        request,
        "news/newsletter_directory.html",
        context,
    )


@login_required
def create_newsletter(request):
    editor = Editor.objects.filter(user=request.user).first()
    journalist = Journalist.objects.filter(user=request.user).first()

    if editor:
        articles = Article.objects.filter(
            publisher=editor.publisher,
            approved_status=True,
            published_status="published",
        )

    elif journalist:
        articles = Article.objects.filter(
            author=journalist,
            approved_status=True,
            published_status="self-published",
        )
    else:
        return HttpResponseForbidden("Not allowed")

    if request.method == "POST":
        title = request.POST.get("title")
        article_ids = request.POST.getlist("articles")

        if not article_ids:
            return render(
                request,
                "news/create_newsletter.html",
                {
                    "error": "At least one article required",
                    "articles": articles,
                },
            )

        if journalist:
            newsletter = Newsletter.objects.create(
                title=title, journalist=journalist
            )
        else:  # editor
            newsletter = Newsletter.objects.create(
                title=title, publisher=editor.publisher
            )

        newsletter.articles.set(article_ids)
        return redirect("news:newsletter_directory")

    return render(
        request,
        "news/create_newsletter.html",
        {"articles": articles},
    )


@login_required
def delete_newsletter(request, newsletter_id):
    """Delete one of the newsletters, if they have the delete
    permission."""
    if not request.user.has_perm("news.delete_newsletter"):
        return redirect("news:journalist_home")  # or show a 403 page

    journalist = Journalist.objects.filter(user=request.user).first()
    editor = Editor.objects.filter(user=request.user).first()

    if editor:
        newsletter = get_object_or_404(
            Newsletter, id=newsletter_id, publisher=editor.publisher
        )
    elif journalist:
        newsletter = get_object_or_404(
            Newsletter, id=newsletter_id, journalist=journalist
        )
    else:
        return HttpResponseForbidden("Not allowed")

    if request.method == "POST":
        newsletter.delete()
        return redirect("news:newsletter_directory")
    else:
        return redirect("news:newsletter_directory")


@login_required
def update_newsletter(request, newsletter_id):
    """Edit one of the newsletters belonging to an editor or journalist.
    On GET the form is shown pre-filled with the current title and articles;
    on POST the changes are saved and the user is returned to the directory.
    """
    journalist = Journalist.objects.filter(user=request.user).first()
    editor = Editor.objects.filter(user=request.user).first()

    # Fetch the newsletter, scoped to whoever owns it, and build the list of
    # articles this user is allowed to choose from.
    if editor:
        newsletter = get_object_or_404(
            Newsletter, id=newsletter_id, publisher=editor.publisher
        )
        articles = Article.objects.filter(
            publisher=editor.publisher,
            approved_status=True,
            published_status="published",
        )
    elif journalist:
        newsletter = get_object_or_404(
            Newsletter, id=newsletter_id, journalist=journalist
        )
        articles = Article.objects.filter(
            author=journalist,
            approved_status=True,
            published_status="self-published",
        )
    else:
        return HttpResponseForbidden("Not allowed")

    if request.method == "POST":
        title = request.POST.get("title")
        article_ids = request.POST.getlist("articles")

        if not article_ids:
            return render(
                request,
                "news/update_newsletter.html",
                {
                    "error": "At least one article required",
                    "newsletter": newsletter,
                    "articles": articles,
                },
            )

        newsletter.title = title
        newsletter.save()
        newsletter.articles.set(article_ids)
        return redirect("news:newsletter_directory")

    return render(
        request,
        "news/update_newsletter.html",
        {
            "newsletter": newsletter,
            "articles": articles,
        },
    )


# ---------------------------------------------------------------------------
# Reader: subscriptions + browsing
# ---------------------------------------------------------------------------
@login_required
def subscription_details(request, subscription_id):
    reader = Reader.objects.filter(user=request.user).first()
    subscription = get_object_or_404(
        Subscription, id=subscription_id, reader=reader
    )

    context = {
        "subscription": subscription,
    }
    return render(request, "news/subscription_details.html", context)


@login_required
def create_subscription(request):
    """Subscribe the logged-in reader to a publisher or a journalist.

    Expects a POST with exactly one of ``publisher`` or ``journalist`` set to
    the target's id. Uses get_or_create so re-subscribing is a no-op rather
    than a UniqueConstraint error.
    """
    reader = Reader.objects.filter(user=request.user).first()
    if reader is None:
        return HttpResponseForbidden("Not allowed")

    if request.method != "POST":
        return redirect("news:find_newsletters")

    publisher_id = request.POST.get("publisher")
    journalist_id = request.POST.get("journalist")

    # The model's check constraint requires exactly one target. Reject the
    # request if neither or both were supplied.
    if bool(publisher_id) == bool(journalist_id):
        return redirect("news:find_newsletters")

    if publisher_id:
        publisher = get_object_or_404(Publisher, pk=publisher_id)
        Subscription.objects.get_or_create(reader=reader, publisher=publisher)
    else:
        journalist = get_object_or_404(Journalist, pk=journalist_id)
        Subscription.objects.get_or_create(
            reader=reader, journalist=journalist
        )

    return redirect("news:reader_home")


@login_required
def article_list(request, subscription_id):
    reader = Reader.objects.filter(user=request.user).first()
    subscription = get_object_or_404(
        Subscription, id=subscription_id, reader=reader
    )
    target = subscription.publisher or subscription.journalist

    if subscription.journalist:
        articles = Article.objects.filter(author=target).order_by(
            "-created_date"
        )
        context = {
            "journalist": target,
            "articles": articles,
        }
    else:  # publisher
        articles = Article.objects.filter(publisher=target).order_by(
            "-created_date"
        )
        context = {
            "publisher": target,
            "articles": articles,
        }

    return render(
        request,
        "news/article_list.html",
        context,
    )


@login_required
def find_newsletters(request):
    """List every publisher and journalist a reader can subscribe to."""
    publishers = Publisher.objects.all().order_by("title")
    journalists = Journalist.objects.all().order_by("user__username")

    context = {
        "publishers": publishers,
        "journalists": journalists,
    }
    return render(request, "news/find_newsletters.html", context)


@login_required
def article_details(request, article_id):
    """Show the article."""
    article = get_object_or_404(Article, id=article_id)
    return render(request, "news/article_details.html", {"article": article})


# ---------------------------------------------------------------------------
# Editor: approvals + publishing
# ---------------------------------------------------------------------------
@editor_required
def article_approvals(request):
    """Show the list of articles for reviewing (editors only)."""
    articles = Article.objects.filter(approved_status=False).order_by(
        "created_date"
    )
    return render(
        request, "news/article_approvals.html", {"articles": articles}
    )


@editor_required
def update_approvals(request):
    """List articles awaiting the editor's publishing decision
    (editors only)."""
    articles = Article.objects.filter(
        published_status="request-publishing"
    ).order_by("created_date")
    return render(
        request, "news/update_approvals.html", {"articles": articles}
    )


@editor_required
def article_review(request, article_id):
    """Show the article for review (editors only)."""
    article = get_object_or_404(Article, id=article_id)
    return render(request, "news/article_review.html", {"article": article})


@editor_required
def publish_articles(request):
    """Show the list of unpublished articles for publishing (editors only)."""
    articles = Article.objects.filter(
        published_status="request-publishing"
    ).order_by("created_date")
    return render(
        request, "news/publish_articles.html", {"articles": articles}
    )


@editor_required
def unpublished_articles(request, article_id):
    """Show the article for publishing (editors only)."""
    article = get_object_or_404(Article, id=article_id)
    return render(
        request, "news/unpublished_articles.html", {"article": article}
    )


@editor_required
def update_published(request):
    """List articles published under this editor's publisher (editors only)."""
    editor = Editor.objects.get(user=request.user)
    articles = Article.objects.filter(
        published_status="published", publisher=editor.publisher
    ).order_by("created_date")
    return render(
        request, "news/update_published.html", {"articles": articles}
    )


def notify_article_approved(request, article):
    """Option-2 side effects to run when an article is approved:
    email the article to subscribers and POST it to our own /api/approved/
    endpoint. Wrapped so a failure here never blocks the approval itself.
    """
    # Gather subscribers of the article's author and (if any) its publisher.
    subscriptions = list(
        article.author.subscribers.select_related("reader__user")
    )
    if article.publisher:
        subscriptions += list(
            article.publisher.subscribers.select_related("reader__user")
        )
    recipient_emails = {
        sub.reader.user.email for sub in subscriptions if sub.reader.user.email
    }

    # 1. Email the approved article to those subscribers.
    if recipient_emails:
        try:
            send_mail(
                subject=f"New article: {article.title}",
                message=f"{article.title}\n\n{article.content}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=list(recipient_emails),
                fail_silently=False,
            )
        except Exception as exc:  # never block approval on an email error
            print(f"[approval] email failed: {exc}")

    # 2. POST the approved article to our own API to log/share it externally.
    try:
        url = request.build_absolute_uri(reverse("news:api_approved_log"))
        payload = ArticleSerializer(article).data
        requests.post(url, json=payload, timeout=5)
    except Exception as exc:  # never block approval on a network error
        print(f"[approval] self-POST failed: {exc}")


@editor_required
def set_article_approval(request, article_id):
    """Approve or un-approve an article (editors only).

    When an article is approved, the Option-2 side effects fire: it is emailed
    to subscribers and POSTed to our own /api/approved/ endpoint.
    """
    article = get_object_or_404(Article, id=article_id)

    if request.method == "POST":
        approved = request.POST.get("approve") == "true"
        article.approved_status = approved
        article.save()

        if approved:
            notify_article_approved(request, article)

    return redirect("news:article_approvals")


@editor_required
def set_article_publishing(request, article_id):
    """Set an article's publishing status (editors only).

    When the new status is "published", the article is tied to the editor's
    own publisher so it shows up in the publisher's article lists and
    newsletters.
    """
    editor = Editor.objects.get(user=request.user)
    article = get_object_or_404(Article, id=article_id)

    if request.method == "POST":
        new_status = request.POST.get("approve")
        if new_status in dict(Article.STATUS_CHOICES):
            article.published_status = new_status
            if new_status == "published":
                article.publisher = editor.publisher
            article.save()

    return redirect("news:article_approvals")


# ---------------------------------------------------------------------------
# Admin: publishers + reader subscriptions
# ---------------------------------------------------------------------------
@staff_member_required
def delete_publisher(request, publisher_id):
    """Delete one of the publishers (admin only)."""
    if not request.user.has_perm("news.delete_publisher"):
        return redirect("news:admin_home")  # or show a 403 page
    publisher = get_object_or_404(Publisher, pk=publisher_id)

    if request.method == "POST":
        publisher.delete()
        return redirect("news:admin_home")
    else:
        return redirect("news:admin_home")


@staff_member_required
def delete_editor(request, editor_id):
    """Delete one of the editors (admin only).

    Removes the underlying User account too; the Editor record is cascade
    deleted along with it.
    """
    if not request.user.has_perm("news.delete_editor"):
        return redirect("news:admin_home")  # or show a 403 page
    editor = get_object_or_404(Editor, pk=editor_id)

    if request.method == "POST":
        editor.user.delete()
        return redirect("news:admin_home")
    else:
        return redirect("news:admin_home")


@login_required
def delete_subscription(request, subscription_id):
    """Delete one of the logged-in reader's own subscriptions."""
    if not request.user.has_perm("news.delete_subscription"):
        return redirect("news:subscription_details", subscription_id)

    reader = Reader.objects.filter(user=request.user).first()
    subscription = get_object_or_404(
        Subscription, pk=subscription_id, reader=reader
    )

    if request.method == "POST":
        subscription.delete()
        return redirect("news:reader_home")
    else:
        return redirect("news:reader_home")


def request_password_reset(request):
    """Handle a "forgot password" request.

    On POST, looks up the user by email and, if found, builds a one-time reset
    link (a signed token) and emails it. With the console email backend in
    development the email is printed to the terminal. The same page is shown
    whether or not the email matched, so no one can probe which emails exist.
    """
    if request.method == "POST":
        email = request.POST.get("email")
        user = User.objects.filter(email=email).first()
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            link = request.build_absolute_uri(
                reverse(
                    "news:password_reset_confirm",
                    kwargs={"uidb64": uid, "token": token},
                )
            )
            send_mail(
                subject="Password Reset",
                message=f"Reset your password here "
                f"(expires in 1 hour):\n\n{link}",
                from_email="your_email@gmail.com",
                recipient_list=[email],
            )
        return render(
            request, "news/password_reset_request.html", {"sent": True}
        )
    return render(request, "news/password_reset_request.html")


def password_reset_confirm(request, uidb64, token):
    """Complete a password reset from the emailed link.

    Decodes the user id and checks the token is valid (and not expired). If so,
    a POST sets the new password and redirects to login; otherwise the page is
    shown with valid=False.
    """
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user and default_token_generator.check_token(user, token):
        if request.method == "POST":
            user.set_password(request.POST.get("password"))
            user.save()
            return redirect("news:login")
        return render(
            request, "news/password_reset_confirm.html", {"valid": True}
        )
    return render(
        request, "news/password_reset_confirm.html", {"valid": False}
    )


@login_required
def publisher_articles(request, publisher_id):
    publisher = get_object_or_404(Publisher, pk=publisher_id)
    articles = Article.objects.filter(
        publisher=publisher, approved_status=True
    ).order_by("-created_date")
    return render(
        request,
        "news/article_list.html",
        {
            "publisher": publisher,
            "articles": articles,
        },
    )


@login_required
def journalist_articles(request, journalist_id):
    journalist = get_object_or_404(Journalist, pk=journalist_id)
    articles = Article.objects.filter(
        author=journalist, approved_status=True
    ).order_by("-created_date")
    return render(
        request,
        "news/article_list.html",
        {
            "journalist": journalist,
            "articles": articles,
        },
    )


@login_required
def email_newsletter(request, newsletter_id):
    """Email a newsletter to every reader subscribed to its journalist
    or its publisher. Only acts on POST to avoid accidental sends."""
    newsletter = get_object_or_404(Newsletter, id=newsletter_id)

    if request.method != "POST":
        return redirect("news:newsletter_directory")

    # Gather subscriptions from whichever target this newsletter belongs to.
    # related_name="subscribers" returns Subscription objects, so we reach
    # the address via subscription.reader.user.email.
    subscriptions = []
    if newsletter.journalist:
        subscriptions += list(
            newsletter.journalist.subscribers.select_related("reader__user")
        )
    if newsletter.publisher:
        subscriptions += list(
            newsletter.publisher.subscribers.select_related("reader__user")
        )

    recipient_emails = {
        sub.reader.user.email for sub in subscriptions if sub.reader.user.email
    }

    if not recipient_emails:
        messages.info(request, "No subscribers found for this newsletter.")
        return redirect("news:newsletter_directory")

    # Newsletter has no body of its own, build one from its articles.
    articles = newsletter.articles.all()
    if articles:
        body = "\n\n".join(
            f"{article.title}\n{article.content}" for article in articles
        )
    else:
        body = "This newsletter currently has no articles."

    send_mail(
        subject=newsletter.title,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=list(recipient_emails),
        fail_silently=False,
    )

    messages.success(
        request,
        f"Newsletter emailed to {len(recipient_emails)} subscriber(s).",
    )
    return redirect("news:newsletter_directory")


# ---------------------------------------------------------------------------
# REST API (Django REST Framework)
#
# These endpoints use HTTP Basic auth and return JSON. Reading is open to any
# authenticated user; creating, updating and deleting articles is restricted
# to the journalist who owns them, mirroring the rules in the HTML views above.
# ---------------------------------------------------------------------------
@api_view(["GET"])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def view_approved_articles(request):
    """Return every editor-approved article as JSON."""
    articles = Article.objects.filter(approved_status=True).order_by(
        "-created_date"
    )
    serializer = ArticleSerializer(articles, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def view_subscribed(request):
    """Return approved articles from the publishers and journalists the
    logged-in reader is subscribed to."""
    try:
        reader = Reader.objects.get(user=request.user)
    except Reader.DoesNotExist:
        return Response(
            {"error": "You must be a reader to view subscribed articles."},
            status=status.HTTP_403_FORBIDDEN,
        )

    subscriptions = Subscription.objects.filter(reader=reader)
    publisher_ids = subscriptions.exclude(publisher=None).values_list(
        "publisher_id", flat=True
    )
    journalist_ids = subscriptions.exclude(journalist=None).values_list(
        "journalist_id", flat=True
    )

    articles = Article.objects.filter(
        Q(publisher_id__in=publisher_ids) | Q(author_id__in=journalist_ids),
        approved_status=True,
    ).order_by("-created_date")
    serializer = ArticleSerializer(articles, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def view_article(request, id):
    """Return a single approved article by id."""
    article = get_object_or_404(Article, id=id, approved_status=True)
    serializer = ArticleSerializer(article)
    return Response(serializer.data)


@api_view(["POST"])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def article_create(request):
    """Create an article for the logged-in journalist."""
    try:
        journalist = Journalist.objects.get(user=request.user)
    except Journalist.DoesNotExist:
        return Response(
            {"error": "You must be a journalist to create an article."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = ArticleSerializer(data=request.data)
    if serializer.is_valid():
        # author comes from the logged-in user; new articles start unapproved
        serializer.save(author=journalist, approved_status=False)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["PUT"])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def article_update(request, id):
    """Update one of the logged-in journalist's own articles."""
    try:
        journalist = Journalist.objects.get(user=request.user)
    except Journalist.DoesNotExist:
        return Response(
            {"error": "You must be a journalist to update an article."},
            status=status.HTTP_403_FORBIDDEN,
        )

    # 404s if the article doesn't exist OR isn't owned by this journalist
    article = get_object_or_404(Article, id=id, author=journalist)

    serializer = ArticleSerializer(article, data=request.data, partial=True)
    if serializer.is_valid():
        # editing un-approves the article, matching the HTML update view
        serializer.save(approved_status=False)
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["DELETE"])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def article_delete(request, id):
    """Delete one of the logged-in journalist's own articles.
    :param int id: The id of the article to be deleted.
    :returns: HTTP responds
    :rtype: django.http.HttpResponse or django.http.HttpResponseRedirect

    """
    try:
        journalist = Journalist.objects.get(user=request.user)
    except Journalist.DoesNotExist:
        return Response(
            {"error": "You must be a journalist to delete an article."},
            status=status.HTTP_403_FORBIDDEN,
        )

    # 404s if the article doesn't exist OR isn't owned by this journalist
    article = get_object_or_404(Article, id=id, author=journalist)
    article.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@authentication_classes([])  # no auth: simulates an external system
@permission_classes([AllowAny])
def approved_log(request):
    """Simulated external receiver for approved articles.

    The approval flow POSTs here to mimic sharing an approved article with an
    outside system, while keeping everything inside this project. It simply
    logs and acknowledges what it received.
    """
    title = request.data.get("title", "(unknown)")
    print(f"[/api/approved/] received approved article: {title}")
    return Response(
        {"status": "logged", "title": title}, status=status.HTTP_200_OK
    )
