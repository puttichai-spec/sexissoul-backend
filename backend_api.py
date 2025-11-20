from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
from datetime import datetime
import requests
import tempfile
from youtube_uploader import YouTubeUploader

app = Flask(__name__)
CORS(app)

# Configuration - ใช้ environment variable
GOFILE_TOKEN = os.environ.get('GOFILE_TOKEN', 'twmq0wCkhFZRu6nMLzMpxKxuOJXL1NYK')
JSONBIN_BIN_ID = os.environ.get('JSONBIN_BIN_ID', '')  # ใส่ Bin ID ที่นี่
JSONBIN_API_KEY = os.environ.get('JSONBIN_API_KEY', '')  # ใส่ API Key ที่นี่

# Validate configuration
if not GOFILE_TOKEN:
    print("WARNING: GOFILE_TOKEN not set!")
if not JSONBIN_BIN_ID or not JSONBIN_API_KEY:
    print("WARNING: JSONBin not configured! Videos won't be saved.")

# JSONBin Helper Functions
def get_videos_from_jsonbin():
    """ดึงข้อมูลวีดีโอจาก JSONBin"""
    try:
        url = f'https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}/latest'
        headers = {
            'X-Master-Key': JSONBIN_API_KEY
        }
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('record', {}).get('videos', [])
        else:
            print(f"JSONBin read error: {response.status_code}")
            return []
    except Exception as e:
        print(f"Error reading from JSONBin: {e}")
        return []

def save_videos_to_jsonbin(videos):
    """บันทึกข้อมูลวีดีโอไป JSONBin"""
    try:
        url = f'https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}'
        headers = {
            'X-Master-Key': JSONBIN_API_KEY,
            'Content-Type': 'application/json'
        }
        data = {'videos': videos}
        response = requests.put(url, json=data, headers=headers, timeout=10)
        
        if response.status_code == 200:
            print("Saved to JSONBin successfully")
            return True
        else:
            print(f"JSONBin save error: {response.status_code}")
            return False
    except Exception as e:
        print(f"Error saving to JSONBin: {e}")
        return False


class VideoUploader:
    def __init__(self):
        self.gofile_token = GOFILE_TOKEN
        self.youtube_uploader = None
        
    def upload_to_gofile(self, video_file):
        """อัปโหลดวีดีโอไปยัง Gofile"""
        try:
            print(f"[Gofile] Starting upload with token: {self.gofile_token[:10]}...")
            
            # Step 1: Get best server
            server_response = requests.get('https://api.gofile.io/servers', timeout=10)
            if server_response.status_code != 200:
                raise Exception(f"ไม่สามารถเชื่อมต่อ Gofile server (status: {server_response.status_code})")
            
            server_data = server_response.json()
            if server_data['status'] != 'ok':
                raise Exception("Gofile API ตอบกลับผิดพลาด")
            
            # Get first available server
            servers = server_data['data']['servers']
            if not servers:
                raise Exception("ไม่มี Gofile server พร้อมใช้งาน")
            
            server = servers[0]['name']
            print(f"[Gofile] Using server: {server}")
            
            # Step 2: Upload file with token
            files = {'file': video_file}
            data = {'token': self.gofile_token}
            
            upload_url = f'https://{server}.gofile.io/contents/uploadfile'
            print(f"[Gofile] Uploading to: {upload_url}")
            
            upload_response = requests.post(
                upload_url, 
                files=files, 
                data=data,
                timeout=300  # 5 minutes timeout
            )
            
            print(f"[Gofile] Upload response status: {upload_response.status_code}")
            
            if upload_response.status_code != 200:
                raise Exception(f"อัปโหลดไปยัง Gofile ล้มเหลว (status: {upload_response.status_code})")
            
            result = upload_response.json()
            print(f"[Gofile] Upload result: {result}")
            
            if result['status'] != 'ok':
                error_msg = result.get('message', 'Unknown error')
                raise Exception(f"Gofile error: {error_msg}")
            
            # Get file ID and download page
            # Note: Gofile API returns 'id' not 'fileId'
            file_id = result['data'].get('id') or result['data'].get('fileId')
            download_url = result['data']['downloadPage']
            print(f"[Gofile] File ID: {file_id}")
            print(f"[Gofile] Download page: {download_url}")
            
            # Try to get direct link
            try:
                print(f"[Gofile] Attempting to get direct link...")
                content_url = f'https://api.gofile.io/contents/{file_id}'
                headers = {
                    'Authorization': f'Bearer {self.gofile_token}'
                }
                
                content_response = requests.get(content_url, headers=headers, timeout=10)
                
                if content_response.status_code == 200:
                    content_data = content_response.json()
                    
                    if content_data.get('status') == 'ok':
                        # Try to get direct link from content
                        data = content_data.get('data', {})
                        
                        # Check if there's a link field
                        if 'link' in data:
                            direct_link = data['link']
                            print(f"[Gofile] Got direct link: {direct_link}")
                            return direct_link
                        
                        # Check contents for files
                        contents = data.get('children', {})
                        if contents:
                            # Get first file's link
                            for child_id, child_data in contents.items():
                                if 'link' in child_data:
                                    direct_link = child_data['link']
                                    print(f"[Gofile] Got direct link from child: {direct_link}")
                                    return direct_link
                
                print(f"[Gofile] Could not get direct link, using download page")
            except Exception as e:
                print(f"[Gofile] Error getting direct link: {e}")
            
            # Fallback to download page
            print(f"[Gofile] Using download page URL: {download_url}")
            return download_url
            
        except requests.Timeout:
            raise Exception("Gofile upload timeout (เกิน 5 นาที)")
        except requests.RequestException as e:
            raise Exception(f"Gofile network error: {str(e)}")
        except Exception as e:
            print(f"[Gofile] Error: {str(e)}")
            raise Exception(f"Gofile upload error: {str(e)}")
    
    def upload_to_youtube(self, video_path, title, tags_str):
        """อัปโหลดวีดีโอไปยัง YouTube - Currently disabled for Railway deployment"""
        raise Exception("YouTube upload ยังไม่พร้อมใช้งาน - ต้อง OAuth authorization ก่อน. กรุณาใช้ Gofile แทน")
        try:
            # Initialize YouTube uploader if not already done
            if self.youtube_uploader is None:
                self.youtube_uploader = YouTubeUploader()
            
            # Prepare tags
            tags = [tag.strip().replace('#', '') for tag in tags_str.split() if tag.strip()]
            
            # Prepare description
            description = f'{title}\n\n{tags_str}\n\n🛒 ซื้อสินค้าได้ที่: https://sexissoul.com\n💬 ปรึกษา LINE: https://lin.ee/xehWIoVw'
            
            # Upload to YouTube
            video_url = self.youtube_uploader.upload_video(
                video_path=video_path,
                title=title,
                description=description,
                tags=tags,
                category_id='22',  # People & Blogs
                privacy_status='public'  # or 'unlisted', 'private'
            )
            
            return video_url
            
        except Exception as e:
            raise Exception(f"YouTube upload error: {str(e)}")

uploader = VideoUploader()

@app.route('/api/upload', methods=['POST'])
def upload_video():
    """API endpoint สำหรับอัปโหลดวีดีโอ"""
    try:
        # Get form data
        title = request.form.get('title')
        tags = request.form.get('tags', '')
        platform = request.form.get('platform', 'gofile')
        shopee_link = request.form.get('shopee', '')
        lazada_link = request.form.get('lazada', '')
        tiktok_link = request.form.get('tiktok', '')
        
        # Get video file
        if 'video' not in request.files:
            return jsonify({'error': 'ไม่พบไฟล์วีดีโอ'}), 400
        
        video_file = request.files['video']
        
        if video_file.filename == '':
            return jsonify({'error': 'ไม่ได้เลือกไฟล์'}), 400
        
        # Validate
        if not title:
            return jsonify({'error': 'กรุณากรอกชื่อวีดีโอ'}), 400
        
        # Save temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(video_file.filename)[1]) as tmp:
            video_file.save(tmp.name)
            tmp_path = tmp.name
        
        video_url = None
        video_url_backup = None
        source = None
        source_backup = None
        
        try:
            # Upload based on platform
            if platform == 'youtube' or platform == 'both':
                video_url = uploader.upload_to_youtube(tmp_path, title, tags)
                source = 'youtube'
            
            if platform == 'gofile' or platform == 'both':
                with open(tmp_path, 'rb') as f:
                    gofile_url = uploader.upload_to_gofile(f)
                    if platform == 'gofile':
                        video_url = gofile_url
                        source = 'gofile'
                    else:
                        video_url_backup = gofile_url
                        source_backup = 'gofile'
            
            # Create video entry
            video_entry = {
                'id': int(datetime.now().timestamp()),
                'title': title,
                'video_url': video_url,
                'source': source,
                'tags': tags,
                'date': datetime.now().isoformat(),
                'shop_links': {
                    'shopee': shopee_link,
                    'lazada': lazada_link,
                    'tiktok': tiktok_link
                },
                'line_url': 'https://lin.ee/xehWIoVw'
            }
            
            if video_url_backup:
                video_entry['video_url_backup'] = video_url_backup
                video_entry['source_backup'] = source_backup
            
            # Load existing videos from JSONBin
            videos = get_videos_from_jsonbin()
            
            # Add new video at the beginning
            videos.insert(0, video_entry)
            
            # Save updated videos to JSONBin
            if not save_videos_to_jsonbin(videos):
                print("Warning: Failed to save to JSONBin")
            
            return jsonify({
                'success': True,
                'message': 'อัปโหลดวีดีโอสำเร็จ!',
                'video': video_entry
            })
            
        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        
    except Exception as e:
        print(f"[ERROR] Upload failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/videos', methods=['GET'])
def get_videos():
    """API endpoint สำหรับดูรายการวีดีโอทั้งหมด"""
    try:
        videos = get_videos_from_jsonbin()
        return jsonify({'videos': videos})
    except Exception as e:
        print(f"Error in get_videos: {e}")
        return jsonify({'videos': [], 'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'message': 'API is running'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
