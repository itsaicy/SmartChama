from django.urls import path
from user.views import home,signup_view,login_view,logout_view,edit_profile,upload_profile_picture, \
activate

urlpatterns = [
    path('', home, name='home'),
    path('login/',login_view, name='login'),
    path('logout/',logout_view, name='logout'),
    path('signup/',signup_view, name='signup'),
    path('profile/',edit_profile, name='profile'),
    path('upload-profile-picture/', upload_profile_picture, name='upload_profile_picture'),
    path('activate/<uidb64>/<token>/', activate, name='activate')

]
