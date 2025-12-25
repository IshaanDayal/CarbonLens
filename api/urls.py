from django.urls import path
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from . import views_refactored

# For async views, we need to use csrf_exempt and require_http_methods
urlpatterns = [
    path('query/', csrf_exempt(require_http_methods(['POST'])(views_refactored.QueryView.as_view())), name='query'),
    path('health/', views_refactored.HealthView.as_view(), name='health'),
    path('greet/', views_refactored.GreetView.as_view(), name='greet'),
    path('news/', csrf_exempt(require_http_methods(['POST'])(views_refactored.NewsView.as_view())), name='news'),
]

