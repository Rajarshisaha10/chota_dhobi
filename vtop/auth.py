import requests
from flask import Blueprint, jsonify, request, make_response, current_app
from bs4 import BeautifulSoup
import uuid
import os
import warnings
from itsdangerous import URLSafeTimedSerializer, BadSignature

# Internal project imports
from .session_manager import session_storage
from .credentials_parser import parse_credentials
from .profile_parser import parse_profile

# Suppress only the InsecureRequestWarning for VIT's internal certificates
warnings.filterwarnings('ignore', category=requests.packages.urllib3.exceptions.InsecureRequestWarning)

auth_bp = Blueprint('auth_bp', __name__)

VTOP_BASE_URL = "https://vtopcc.vit.ac.in/vtop/"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:149.0) Gecko/20100101 Firefox/149.0'
}

def get_serializer():
    """Returns a serializer for encrypting/decrypting credentials in cookies."""
    return URLSafeTimedSerializer(current_app.secret_key)

def perform_vtop_login(api_session, csrf_token, username, password, captcha_text, session_id):
    """
    Executes the actual VTOP login request.
    """
    try:
        payload = {"_csrf": csrf_token, "username": username, "password": password, "captchaStr": captcha_text}
        login_url = VTOP_BASE_URL + "login"
        
        response = api_session.post(login_url, data=payload, headers=HEADERS, verify=False, timeout=20)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        login_form = soup.find('form', {'id': 'vtopLoginForm'})

        if not login_form:
            # Login successful: Extract new CSRF and authorizedID
            authorized_id = username 
            auth_id_tag = soup.find('input', {'name': 'authorizedID'}) or soup.find('input', {'name': 'authorizedIDX'})
            if auth_id_tag and auth_id_tag.get('value'):
                 authorized_id = auth_id_tag.get('value')
            
            session_storage[session_id]['username'] = username
            session_storage[session_id]['authorized_id'] = authorized_id
            
            # Update CSRF token for subsequent requests
            new_csrf_tag = soup.find('input', {'name': '_csrf'})
            if new_csrf_tag and new_csrf_tag.get('value'):
                session_storage[session_id]['csrf_token'] = new_csrf_tag.get('value')
                print(f"Login success: {authorized_id}, CSRF updated.")
            else:
                print(f"Login success: {authorized_id}, but CSRF tag not found in response.")
            
            return True, authorized_id, 'success'
        else:
            error_tag = soup.select_one("span.text-danger strong")
            error_msg = error_tag.get_text(strip=True) if error_tag else "Invalid credentials."
            print(f"Login failed: {error_msg}")
            return False, error_msg, 'invalid_credentials'

    except Exception as e:
        print(f"Login exception: {str(e)}")
        return False, str(e), 'error'

@auth_bp.route('/start-login', methods=['POST'])
def start_login():
    session_id = str(uuid.uuid4())
    api_session = requests.Session()
    try:
        res = api_session.get(VTOP_BASE_URL + "open/page", headers=HEADERS, verify=False)
        csrf_pre = BeautifulSoup(res.text, 'html.parser').find('input', {'name': '_csrf'}).get('value')
        
        res = api_session.post(VTOP_BASE_URL + "prelogin/setup", data={'_csrf': csrf_pre, 'flag': 'VTOP'}, verify=False)
        csrf_login = BeautifulSoup(res.text, 'html.parser').find('input', {'name': '_csrf'}).get('value')
        
        captcha_res = api_session.get(VTOP_BASE_URL + "get/new/captcha", verify=False)
        captcha_src = BeautifulSoup(captcha_res.text, 'html.parser').find('img')['src']

        session_storage[session_id] = {'session': api_session, 'csrf_token': csrf_login}
        return jsonify({'status': 'captcha_ready', 'session_id': session_id, 'captcha_image_data': captcha_src})
    except Exception as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 500

@auth_bp.route('/login-attempt', methods=['POST'])
def login_attempt():
    data = request.json
    s_id = data.get('session_id')
    if s_id not in session_storage:
        return jsonify({'status': 'failure', 'message': 'Session expired.'}), 400
        
    success, result, code = perform_vtop_login(
        session_storage[s_id]['session'], session_storage[s_id]['csrf_token'], 
        data.get('username'), data.get('password'), data.get('captcha'), s_id
    )
    
    if success:
        resp = make_response(jsonify({'status': 'success', 'message': f'Welcome, {result}!', 'session_id': s_id}))
        token = get_serializer().dumps({'u': data.get('username'), 'p': data.get('password')})
        resp.set_cookie('vtop_creds', token, httponly=True, max_age=2592000, samesite='Lax')
        resp.set_cookie('session_id', s_id, httponly=True, max_age=3600, samesite='Lax')
        return resp
    return jsonify({'status': code, 'message': result})

@auth_bp.route('/api/credentials', methods=['GET'])
def get_credentials_api():
    session_id = request.cookies.get('session_id')
    if not session_id or session_id not in session_storage:
        return jsonify({'status': 'failure', 'message': 'Invalid session.'}), 400

    api_session = session_storage[session_id]['session']
    try:
        creds_url = VTOP_BASE_URL + "proctor/viewStudentCredentials"
        csrf_token = session_storage[session_id]['csrf_token']
        authorized_id = session_storage[session_id].get('authorized_id')
        if not authorized_id:
            authorized_id = session_storage[session_id].get('username')
        if not authorized_id:
            authorized_id = session_storage[session_id].get('username')
        
        headers = HEADERS.copy()
        headers['Referer'] = VTOP_BASE_URL + "home"
        
        print(f"Fetching credentials for {authorized_id}...")
        response = api_session.post(
            creds_url, 
            data={'_csrf': csrf_token, 'authorizedID': authorized_id}, 
            headers=headers, verify=False, timeout=20
        )
        response.raise_for_status()
        data = parse_credentials(response.text)
        return jsonify(data)
    except Exception as e:
        print(f"Error fetching credentials for session {session_id}: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@auth_bp.route('/api/profile', methods=['GET'])
def get_profile_api():
    session_id = request.cookies.get('session_id')
    if not session_id or session_id not in session_storage:
        return jsonify({'status': 'failure', 'message': 'Invalid session.'}), 400

    api_session = session_storage[session_id]['session']
    try:
        # VTOP Profile View URL
        profile_url = VTOP_BASE_URL + "studentsRecord/StudentProfileAllView"
        csrf_token = session_storage[session_id]['csrf_token']
        authorized_id = session_storage[session_id].get('authorized_id')
        
        headers = HEADERS.copy()
        headers['Referer'] = VTOP_BASE_URL + "home"
        
        # Profile page usually requires a POST with CSRF too
        response = api_session.post(
            profile_url, 
            data={'_csrf': csrf_token, 'authorizedID': authorized_id}, 
            headers=headers, verify=False, timeout=20
        )
        response.raise_for_status()

        data = parse_profile(response.text)
        
        # Ensure registration number is correct (always prefer authorized_id from login)
        if 'educational' not in data: data['educational'] = {}
        data['educational']['reg_no'] = session_storage[session_id].get('username', authorized_id)
            
        return jsonify(data)
    except Exception as e:
        print(f"Error fetching profile for session {session_id}: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@auth_bp.route('/save-credentials-txt', methods=['POST'])
def save_credentials_txt():
    """
    Fetches credentials using the verified proctor endpoint and saves to TXT.
    """
    session_id = request.json.get('session_id')
    if not session_id or session_id not in session_storage:
        return jsonify({'status': 'failure', 'message': 'Invalid session.'}), 400

    api_session = session_storage[session_id]['session']
    try:
        # Verified endpoint from your network log
        creds_url = VTOP_BASE_URL + "proctor/viewStudentCredentials"
        csrf_token = session_storage[session_id]['csrf_token']
        
        # VTOP requires a POST with CSRF for this data
        response = api_session.post(creds_url, data={'_csrf': csrf_token}, headers=HEADERS, verify=False, timeout=20)
        response.raise_for_status()

        data = parse_credentials(response.text)
        file_name = f"vtop_creds_{session_id[:8]}.txt"
        
        with open(file_name, "w", encoding="utf-8") as f:
            f.write("=== VTOP STUDENT CREDENTIALS ===\n\n")
            for acc in data.get('accounts', []):
                f.write(f"Account:  {acc['account']}\nUsername: {acc['username']}\nPassword: {acc['password']}\n")
                f.write("-" * 30 + "\n")
            
            f.write("\n=== EXAM SCHEDULE ===\n")
            for exam in data.get('exams', []):
                f.write(f"Exam:   {exam['account']}\nVenue:  {exam['venue_date']}\nSeat:   {exam['seat']}\nPassword: {exam['password']}\n")
                f.write("-" * 30 + "\n")

        return jsonify({'status': 'success', 'message': f'Credentials saved to {file_name}'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@auth_bp.route('/logout', methods=['POST'])
def logout():
    session_id = request.json.get('session_id')
    if session_id in session_storage:
        del session_storage[session_id]
    resp = make_response(jsonify({'status': 'success'}))
    resp.delete_cookie('vtop_creds')
    return resp
