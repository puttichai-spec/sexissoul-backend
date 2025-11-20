"""
YouTube Uploader with OAuth2 Authentication
"""
import os
import pickle
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
CLIENT_SECRETS_FILE = 'client_secret.json'
TOKEN_PICKLE_FILE = 'token.pickle'

class YouTubeUploader:
    def __init__(self):
        self.credentials = None
        self.youtube = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with YouTube API"""
        # Load saved credentials
        if os.path.exists(TOKEN_PICKLE_FILE):
            with open(TOKEN_PICKLE_FILE, 'rb') as token:
                self.credentials = pickle.load(token)
        
        # If no valid credentials, get new ones
        if not self.credentials or not self.credentials.valid:
            if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                self.credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    CLIENT_SECRETS_FILE, SCOPES)
                self.credentials = flow.run_local_server(port=0)
            
            # Save credentials for next run
            with open(TOKEN_PICKLE_FILE, 'wb') as token:
                pickle.dump(self.credentials, token)
        
        # Build YouTube service
        self.youtube = build('youtube', 'v3', credentials=self.credentials)
    
    def upload_video(self, video_path, title, description='', tags=None, category_id='22', privacy_status='public'):
        """
        Upload video to YouTube
        
        Args:
            video_path: Path to video file
            title: Video title
            description: Video description
            tags: List of tags
            category_id: YouTube category ID (22 = People & Blogs)
            privacy_status: 'public', 'private', or 'unlisted'
        
        Returns:
            Video URL
        """
        if tags is None:
            tags = []
        
        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags,
                'categoryId': category_id
            },
            'status': {
                'privacyStatus': privacy_status,
                'selfDeclaredMadeForKids': False
            }
        }
        
        # Create media upload
        media = MediaFileUpload(
            video_path,
            chunksize=-1,
            resumable=True,
            mimetype='video/*'
        )
        
        # Execute upload
        request = self.youtube.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=media
        )
        
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"Upload progress: {int(status.progress() * 100)}%")
        
        video_id = response['id']
        video_url = f'https://www.youtube.com/watch?v={video_id}'
        
        return video_url

def test_upload():
    """Test function"""
    uploader = YouTubeUploader()
    
    # Example
    video_url = uploader.upload_video(
        video_path='test_video.mp4',
        title='Test Video',
        description='This is a test video',
        tags=['test', 'demo'],
        privacy_status='unlisted'
    )
    
    print(f'Video uploaded: {video_url}')

if __name__ == '__main__':
    test_upload()
