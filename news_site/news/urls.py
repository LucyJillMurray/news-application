"""URL configuration for the news app.

Every name below matches the ``news:<name>`` references used throughout the
templates and the ``reverse``/``redirect`` calls in views.py. The patterns are
grouped by area (auth, registration, role home pages, articles, newsletters,
subscriptions and editor review tools) to keep them easy to scan.
"""

from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

app_name = "news"

urlpatterns = [
    path("", views.login_user, name="login"),
    # Authentication
    path("logout/", views.logout_user, name="logout"),
    # Registration
    path("register/reader/", views.register_reader, name="register_reader"),
    path(
        "register/journalist/",
        views.register_journalist,
        name="register_journalist",
    ),
    path(
        "register/publisher/",
        views.register_publisher,
        name="register_publisher",
    ),
    path("register/editor/", views.register_editor, name="register_editor"),
    # Role home pages / dashboards
    path("reader/", views.reader_home, name="reader_home"),
    path("journalist/", views.journalist_home, name="journalist_home"),
    path("editor/", views.editor_home, name="editor_home"),
    path("publisher/", views.publisher_home, name="publisher_home"),
    path(
        "admin-dashboard/",
        views.admin_home,
        name="admin_home",
    ),
    path(
        "article-dashboard/",
        views.article_dashboard,
        name="article_dashboard",
    ),
    # Articles
    path("articles/", views.article_directory, name="article_directory"),
    path("articles/create/", views.create_article, name="create_article"),
    path(
        "articles/<int:article_id>/",
        views.article_details,
        name="article_details",
    ),
    path(
        "subscriptions/create/",
        views.create_subscription,
        name="create_subscription",
    ),
    path(
        "publishers/<int:publisher_id>/articles/",
        views.publisher_articles,
        name="publisher_articles",
    ),
    path(
        "journalists/<int:journalist_id>/articles/",
        views.journalist_articles,
        name="journalist_articles",
    ),
    path(
        "articles/<int:article_id>/update/",
        views.update_article,
        name="update_article",
    ),
    path(
        "articles/<int:article_id>/delete/",
        views.delete_article,
        name="delete_article",
    ),
    # Newsletters
    path(
        "newsletters/",
        views.newsletter_directory,
        name="newsletter_directory",
    ),
    path(
        "newsletters/create/",
        views.create_newsletter,
        name="create_newsletter",
    ),
    path(
        "newsletters/<int:newsletter_id>/update/",
        views.update_newsletter,
        name="update_newsletter",
    ),
    path(
        "newsletters/<int:newsletter_id>/delete/",
        views.delete_newsletter,
        name="delete_newsletter",
    ),
    path("find-newsletters/", views.find_newsletters, name="find_newsletters"),
    # Subscriptions
    path(
        "subscriptions/<int:subscription_id>/",
        views.subscription_details,
        name="subscription_details",
    ),
    path(
        "subscriptions/<int:subscription_id>/articles/",
        views.article_list,
        name="article_list",
    ),
    path(
        "subscriptions/<int:subscription_id>/delete/",
        views.delete_subscription,
        name="delete_subscription",
    ),
    path(
        "newsletters/<int:newsletter_id>/email/",
        views.email_newsletter,
        name="email_newsletter",
    ),
    # Editor review / publishing tools
    path("approvals/", views.article_approvals, name="article_approvals"),
    path("approvals/update/", views.update_approvals, name="update_approvals"),
    path(
        "articles/<int:article_id>/review/",
        views.article_review,
        name="article_review",
    ),
    path(
        "articles/<int:article_id>/approve/",
        views.set_article_approval,
        name="set_article_approval",
    ),
    path(
        "articles/<int:article_id>/publish/",
        views.set_article_publishing,
        name="set_article_publishing",
    ),
    path("publish/", views.publish_articles, name="publish_articles"),
    path(
        "articles/<int:article_id>/unpublished/",
        views.unpublished_articles,
        name="unpublished_articles",
    ),
    path("published/update/", views.update_published, name="update_published"),
    # Publisher administration
    path(
        "publisher/<int:publisher_id>/delete/",
        views.delete_publisher,
        name="delete_publisher",
    ),
    path(
        "publisher/editor/<int:editor_id>/delete/",
        views.delete_editor,
        name="delete_editor",
    ),
    path(
        "password-reset/",
        views.request_password_reset,
        name="request_password_reset",
    ),
    path(
        "password-reset/<uidb64>/<token>/",
        views.password_reset_confirm,
        name="password_reset_confirm",
    ),
    # API
    path("api/approved/", views.approved_log, name="api_approved_log"),
    path(
        "api/articles/",
        views.view_approved_articles,
        name="api_view_approved_articles",
    ),
    path(
        "api/articles/subscribed/",
        views.view_subscribed,
        name="api_view_subscribed",
    ),
    path(
        "api/articles/create/",
        views.article_create,
        name="api_article_create",
    ),
    path(
        "api/articles/<int:id>/",
        views.view_article,
        name="api_view_article",
    ),
    path(
        "api/articles/<int:id>/update/",
        views.article_update,
        name="api_article_update",
    ),
    path(
        "api/articles/<int:id>/delete/",
        views.article_delete,
        name="api_article_delete",
    ),
]
