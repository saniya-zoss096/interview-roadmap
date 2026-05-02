# app.py
import os
import json
import base64
import io
import hashlib
from datetime import datetime, timedelta

import uuid
import numpy as np
import pandas as pd
import cv2
import mediapipe as mp
from flask import (
    Flask, render_template, request, jsonify, session, redirect, url_for, send_file
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, login_required, logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

import requests
from bs4 import BeautifulSoup
from serpapi import GoogleSearch
from github import Github

# Check mediapipe version and handle compatibility
import mediapipe as mp
print(f"MediaPipe version: {mp.__version__}")

# Verify solutions module is available
try:
    from mediapipe.python.solutions import pose as mp_pose
    from mediapipe.python.solutions import face_mesh as mp_face_mesh
    print("MediaPipe solutions loaded successfully")
except ImportError:
    try:
        from mediapipe import solutions
        mp_pose = solutions.pose
        mp_face_mesh = solutions.face_mesh
        print("MediaPipe solutions loaded (alternative method)")
    except ImportError:
        print("MediaPipe solutions module not found")
        mp_pose = None
        mp_face_mesh = None

# Import optional: APScheduler for periodic updates (not mandatory)
# from apscheduler.schedulers.background import BackgroundScheduler
 
app = Flask(__name__)

# os.environ.get() will now find variables from .env file
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super-secret-key-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///interview_roadmap.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


#INITIALIZE EXTENSIONS
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ========== VERIFY ENVIRONMENT VARIABLES (Optional but helpful) ==========
print("=" * 50)
print("Environment Check:")
print(f"SECRET_KEY loaded: {'Yes' if os.environ.get('SECRET_KEY') else 'No'}")
print(f"SERPAPI_KEY loaded: {'Yes' if os.environ.get('SERPAPI_KEY') else 'No'}")
print(f"GITHUB_TOKEN loaded: {'Yes' if os.environ.get('GITHUB_TOKEN') else 'No'}")
print("=" * 50)

# ================== DATABASE MODELS ==================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    full_name = db.Column(db.String(200))
    target_field = db.Column(db.String(100))
    professional_level = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    exam_scores = db.relationship('ExamScore', backref='user', lazy=True)
    certifications = db.relationship('Certification', backref='user', lazy=True)
    interview_sessions = db.relationship('InterviewSession', backref='user', lazy=True)
    course_progress = db.relationship('UserCourseProgress', backref='user', lazy=True)

class ExamScore(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    subject = db.Column(db.String(100))
    theory_marks = db.Column(db.Float)
    practical_marks = db.Column(db.Float)
    understanding_level = db.Column(db.Integer)
    semester = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Certification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    course_name = db.Column(db.String(200))
    platform = db.Column(db.String(100))
    field = db.Column(db.String(100))
    completion_status = db.Column(db.String(50))
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)

class InterviewSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    session_date = db.Column(db.DateTime, default=datetime.utcnow)
    posture_score = db.Column(db.Float)
    eye_contact_score = db.Column(db.Float)
    body_language_score = db.Column(db.Float)
    overall_feedback = db.Column(db.Text)
    duration = db.Column(db.Integer)

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    field = db.Column(db.String(100))
    difficulty_level = db.Column(db.Integer)
    badge_image = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)
    source_platform = db.Column(db.String(50))     # 'nptel', 'coursera', 'github'
    source_id = db.Column(db.String(200))
    source_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    lessons = db.relationship('Lesson', backref='course', lazy=True, cascade='all, delete-orphan')
    quizzes = db.relationship('Quiz', backref='course', lazy=True, cascade='all, delete-orphan')

class Lesson(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content_type = db.Column(db.String(20), default='video')
    content_url = db.Column(db.String(500))
    content_text = db.Column(db.Text)
    order = db.Column(db.Integer, nullable=False)
    duration_minutes = db.Column(db.Integer, default=10)

class Quiz(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    title = db.Column(db.String(200))
    passing_score = db.Column(db.Float, default=70.0)
    questions = db.relationship('QuizQuestion', backref='quiz', lazy=True, cascade='all, delete-orphan')

class QuizQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    options = db.Column(db.Text)            # JSON list
    correct_answer = db.Column(db.String(500))

class UserCourseProgress(db.Model):
    __table_args__ = (db.UniqueConstraint('user_id', 'course_id', name='_user_course_uc'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed = db.Column(db.Boolean, default=False)
    completed_date = db.Column(db.DateTime)
    last_accessed = db.Column(db.DateTime, default=datetime.utcnow)
    completed_lessons = db.Column(db.Text, default='[]')
    quiz_scores = db.Column(db.Text, default='{}')

class Certificate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    issued_date = db.Column(db.DateTime, default=datetime.utcnow)
    verification_code = db.Column(db.String(64), unique=True, nullable=False)
    pdf_url = db.Column(db.String(500))

class Resume(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    template_version = db.Column(db.String(50))
    content = db.Column(db.JSON)
    ats_score = db.Column(db.Float)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    industry = db.Column(db.String(100))
    format_type = db.Column(db.String(50))

class MarketTrend(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    field = db.Column(db.String(100))
    trend_data = db.Column(db.JSON)
    last_updated = db.Column(db.DateTime)
    source = db.Column(db.String(200))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ================== SERVICES ==================

# Academic assessment (unchanged)
class AcademicAssessor:
    def __init__(self):
        self.levels = {
            1: "Beginner - Needs fundamental strengthening",
            2: "Intermediate - Building core competencies",
            3: "Advanced - Ready for specialized roles",
            4: "Expert - Industry-ready professional"
        }

    def assess_professional_level(self, scores_data):
        avg_theory = np.mean([s.theory_marks for s in scores_data]) if scores_data else 0
        avg_practical = np.mean([s.practical_marks for s in scores_data]) if scores_data else 0
        avg_understanding = np.mean([s.understanding_level for s in scores_data]) if scores_data else 0
        total_score = avg_theory * 0.3 + avg_practical * 0.4 + avg_understanding * 0.3
        if total_score >= 85:
            level = 4
        elif total_score >= 70:
            level = 3
        elif total_score >= 55:
            level = 2
        else:
            level = 1
        return {
            'level': level,
            'description': self.levels[level],
            'scores': {'theory': avg_theory, 'practical': avg_practical, 'understanding': avg_understanding}
        }

    def generate_study_plan(self, scores_data, target_field):
        weak_subjects = []
        strong_subjects = []
        for score in scores_data:
            if score.theory_marks < 60 or score.practical_marks < 60:
                weak_subjects.append(score.subject)
            else:
                strong_subjects.append(score.subject)
        plan = {
            'focus_areas': weak_subjects,
            'strengths': strong_subjects,
            'recommendations': self._get_field_recommendations(target_field, weak_subjects)
        }
        return plan

    def _get_field_recommendations(self, field, weak_subjects):
        recs = {
            'Software Development': ['Data Structures', 'Algorithms', 'System Design'],
            'Data Science': ['Statistics', 'Machine Learning', 'Deep Learning'],
            'Web Development': ['HTML/CSS', 'JavaScript', 'React/Node.js'],
            'Networking': ['CCNA', 'Network Security', 'Cloud Computing']
        }
        return recs.get(field, recs['Software Development'])

# Interview analyzer with privacy (unchanged)
class InterviewAnalyzer:
    def __init__(self):
        import mediapipe as mp
        print(f"MediaPipe version: {mp.__version__}")
        
        self.mp_pose = mp.solutions.pose
        self.mp_face_mesh = mp.solutions.face_mesh
        self.mp_drawing = mp.solutions.drawing_utils
        
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            smooth_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        
        # OpenCV face cascade for blurring (backup)
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        
        print("MediaPipe initialized successfully!")

    def analyze_frame(self, frame):
        """Analyze posture, eye contact, and body language with privacy"""
        # Step 1: Blur face for privacy
        frame = self._blur_face_with_mediapipe(frame)
        
        # Step 2: Convert to RGB for MediaPipe
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb_frame.flags.writeable = False
        
        # Step 3: Process with MediaPipe
        pose_results = self.pose.process(rgb_frame)
        face_results = self.face_mesh.process(rgb_frame)
        
        rgb_frame.flags.writeable = True
        
        # Step 4: Analyze results
        posture_score = self._analyze_posture(pose_results)
        eye_contact_score = self._analyze_eye_contact(face_results)
        body_language_score = self._analyze_body_language(pose_results)
        
        # Step 5: Generate feedback
        feedback = self._generate_feedback(posture_score, eye_contact_score, body_language_score)
        
        return {
            'posture_score': round(posture_score, 1),
            'eye_contact_score': round(eye_contact_score, 1),
            'body_language_score': round(body_language_score, 1),
            'feedback': feedback
        }

    def _blur_face_with_mediapipe(self, frame):
        """Use MediaPipe to precisely detect and blur face for privacy"""
        try:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.face_mesh.process(rgb_frame)
            
            if results.multi_face_landmarks:
                h, w, _ = frame.shape
                for face_landmarks in results.multi_face_landmarks:
                    # Get face bounding box from landmarks
                    x_min = w
                    y_min = h
                    x_max = 0
                    y_max = 0
                    
                    for landmark in face_landmarks.landmark:
                        x = int(landmark.x * w)
                        y = int(landmark.y * h)
                        x_min = min(x_min, x)
                        y_min = min(y_min, y)
                        x_max = max(x_max, x)
                        y_max = max(y_max, y)
                    
                    # Add padding
                    padding = 30
                    x_min = max(0, x_min - padding)
                    y_min = max(0, y_min - padding)
                    x_max = min(w, x_max + padding)
                    y_max = min(h, y_max + padding)
                    
                    # Extract and blur face region
                    if x_max > x_min and y_max > y_min:
                        face_region = frame[y_min:y_max, x_min:x_max]
                        if face_region.size > 0:
                            blurred_face = cv2.GaussianBlur(face_region, (99, 99), 30)
                            frame[y_min:y_max, x_min:x_max] = blurred_face
        except Exception as e:
            # Fallback to OpenCV face detection for blurring
            try:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = self.face_cascade.detectMultiScale(gray, 1.1, 4)
                for (x, y, w, h) in faces:
                    face_region = frame[y:y+h, x:x+w]
                    if face_region.size > 0:
                        blurred_face = cv2.GaussianBlur(face_region, (99, 99), 30)
                        frame[y:y+h, x:x+w] = blurred_face
            except:
                pass
        
        return frame

    def _analyze_posture(self, pose_results):
        """Analyze posture based on shoulder alignment and body position"""
        if not pose_results.pose_landmarks:
            return 40  # No person detected
        
        try:
            landmarks = pose_results.pose_landmarks.landmark
            
            # Get key landmarks
            left_shoulder = landmarks[self.mp_pose.PoseLandmark.LEFT_SHOULDER.value]
            right_shoulder = landmarks[self.mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
            left_ear = landmarks[self.mp_pose.PoseLandmark.LEFT_EAR.value]
            right_ear = landmarks[self.mp_pose.PoseLandmark.RIGHT_EAR.value]
            nose = landmarks[self.mp_pose.PoseLandmark.NOSE.value]
            
            # Check 1: Shoulder alignment (horizontal)
            shoulder_slope = abs(left_shoulder.y - right_shoulder.y)
            shoulder_score = max(0, 100 - (shoulder_slope * 200))
            
            # Check 2: Head position (should be centered between shoulders)
            shoulder_mid_x = (left_shoulder.x + right_shoulder.x) / 2
            head_offset = abs(nose.x - shoulder_mid_x)
            head_score = max(0, 100 - (head_offset * 200))
            
            # Check 3: Upper body visibility
            visibility_score = min(
                left_shoulder.visibility * 100,
                right_shoulder.visibility * 100
            )
            
            # Combined posture score
            posture_score = (shoulder_score * 0.4) + (head_score * 0.3) + (visibility_score * 0.3)
            
            return min(100, max(0, posture_score))
            
        except Exception as e:
            print(f"Posture analysis error: {e}")
            return 50

    def _analyze_eye_contact(self, face_results):
        """Analyze eye contact based on face orientation and eye position"""
        if not face_results.multi_face_landmarks:
            return 20  # No face detected
        
        try:
            face_landmarks = face_results.multi_face_landmarks[0]
            
            # Key landmarks for eye contact
            nose_tip = face_landmarks.landmark[1]
            left_eye_outer = face_landmarks.landmark[33]
            right_eye_outer = face_landmarks.landmark[263]
            left_eye_inner = face_landmarks.landmark[133]
            right_eye_inner = face_landmarks.landmark[362]
            
            # Check 1: Face centering (is the face centered in frame?)
            center_score = 100 - abs(nose_tip.x - 0.5) * 200
            
            # Check 2: Face distance (too close or too far?)
            # z-coordinate indicates distance from camera
            face_size = abs(right_eye_outer.x - left_eye_outer.x)
            if 0.15 < face_size < 0.35:
                distance_score = 90
            elif 0.10 < face_size < 0.40:
                distance_score = 70
            else:
                distance_score = 50
            
            # Check 3: Head tilt (should be minimal)
            eye_slope = abs(left_eye_outer.y - right_eye_outer.y)
            tilt_score = max(0, 100 - (eye_slope * 300))
            
            # Check 4: Eyes visible (are both eyes detected?)
            eye_visibility = min(nose_tip.visibility * 100, 100)
            
            # Combined eye contact score
            eye_contact_score = (
                center_score * 0.35 +
                distance_score * 0.25 +
                tilt_score * 0.20 +
                eye_visibility * 0.20
            )
            
            return min(100, max(0, eye_contact_score))
            
        except Exception as e:
            print(f"Eye contact analysis error: {e}")
            return 30

    def _analyze_body_language(self, pose_results):
        """Analyze body language based on arm position and overall posture"""
        if not pose_results.pose_landmarks:
            return 30  # No person detected
        
        try:
            landmarks = pose_results.pose_landmarks.landmark
            
            # Get arm landmarks
            left_shoulder = landmarks[self.mp_pose.PoseLandmark.LEFT_SHOULDER.value]
            right_shoulder = landmarks[self.mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
            left_elbow = landmarks[self.mp_pose.PoseLandmark.LEFT_ELBOW.value]
            right_elbow = landmarks[self.mp_pose.PoseLandmark.RIGHT_ELBOW.value]
            left_wrist = landmarks[self.mp_pose.PoseLandmark.LEFT_WRIST.value]
            right_wrist = landmarks[self.mp_pose.PoseLandmark.RIGHT_WRIST.value]
            
            # Check 1: Hands visibility
            hands_visible = (
                left_wrist.visibility > 0.5 and 
                right_wrist.visibility > 0.5
            )
            
            # Check 2: Arms not crossed
            arms_open = (
                left_wrist.x < left_elbow.x and 
                right_wrist.x > right_elbow.x
            )
            
            # Check 3: Arms not too close to body
            left_arm_extended = abs(left_wrist.x - left_shoulder.x) > 0.1
            right_arm_extended = abs(right_wrist.x - right_shoulder.x) > 0.1
            
            # Check 4: Hands above waist (not in pockets)
            hands_visible_position = (
                left_wrist.y < landmarks[self.mp_pose.PoseLandmark.LEFT_HIP.value].y and
                right_wrist.y < landmarks[self.mp_pose.PoseLandmark.RIGHT_HIP.value].y
            )
            
            # Calculate score
            score = 0
            if hands_visible:
                score += 30
            if arms_open:
                score += 25
            if left_arm_extended and right_arm_extended:
                score += 25
            if hands_visible_position:
                score += 20
            
            return min(100, score)
            
        except Exception as e:
            print(f"Body language analysis error: {e}")
            return 40

    def _generate_feedback(self, posture_score, eye_contact_score, body_language_score):
        """Generate specific, constructive feedback based on scores"""
        feedback = []
        
        # Posture feedback
        if posture_score < 40:
            feedback.append("⚠️ Sit up straight and face the camera directly")
        elif posture_score < 60:
            feedback.append("💡 Try to straighten your shoulders for better posture")
        elif posture_score < 75:
            feedback.append("👍 Your posture is decent - keep your shoulders level")
        
        # Eye contact feedback
        if eye_contact_score < 40:
            feedback.append("⚠️ Look directly at the camera - eye contact is crucial")
        elif eye_contact_score < 60:
            feedback.append("💡 Try to maintain more consistent eye contact with the camera")
        elif eye_contact_score < 75:
            feedback.append("👍 Good eye contact - keep your gaze steady")
        
        # Body language feedback
        if body_language_score < 40:
            feedback.append("⚠️ Keep your hands visible and maintain an open posture")
        elif body_language_score < 60:
            feedback.append("💡 Try to appear more open - uncross your arms if crossed")
        elif body_language_score < 75:
            feedback.append("👍 Your body language is good - stay relaxed and open")
        
        # Overall positive feedback if all scores are good
        if not feedback:
            avg_score = (posture_score + eye_contact_score + body_language_score) / 3
            if avg_score >= 80:
                feedback.append("🌟 Excellent! You're presenting yourself very professionally")
            elif avg_score >= 70:
                feedback.append("✅ Good job! You're interview-ready with minor improvements")
            else:
                feedback.append("✅ You're on the right track - keep practicing!")
        
        return feedback

    def __del__(self):
        """Clean up MediaPipe resources"""
        try:
            if hasattr(self, 'pose') and self.pose:
                self.pose.close()
            if hasattr(self, 'face_mesh') and self.face_mesh:
                self.face_mesh.close()
            print("MediaPipe resources cleaned up")
        except Exception as e:
            print(f"Cleanup error: {e}")

# Real-time market intelligence
class MarketIntelligenceService:
    def __init__(self):
        self.serpapi_key = os.environ.get('SERPAPI_KEY')
        self.cache = {}  # in-memory cache; in production use Redis

    def get_trending_technologies(self, field):
        cache_key = f"trends_{field}"
        if cache_key in self.cache and (datetime.utcnow() - self.cache[cache_key]['timestamp']).seconds < 3600:
            return self.cache[cache_key]['data']
        try:
            params = {
                "engine": "google_trends",
                "q": f"{field} technologies 2024",
                "api_key": self.serpapi_key,
                "data_type": "TIMESERIES"
            }
            search = GoogleSearch(params)
            results = search.get_dict()
            job_params = {
                "engine": "google_jobs",
                "q": f"{field} jobs",
                "api_key": self.serpapi_key,
                "location": "India"
            }
            job_search = GoogleSearch(job_params)
            job_results = job_search.get_dict()
            trending_skills = self._extract_skills(job_results)
            data = {
                'trends': results.get('interest_over_time', {}),
                'trending_skills': trending_skills,
                'demand_score': min(100, len(job_results.get('jobs_results', []))),
                'timestamp': datetime.utcnow()
            }
            self.cache[cache_key] = {'data': data, 'timestamp': datetime.utcnow()}
            return data
        except Exception as e:
            print(f"MarketIntelligence error: {e}")
            return {'trending_skills': [], 'demand_score': 0, 'trends': {}}

    def _extract_skills(self, job_results):
        from collections import Counter
        skill_keywords = [
            'python', 'java', 'javascript', 'react', 'node.js', 'aws', 'azure',
            'machine learning', 'artificial intelligence', 'docker', 'kubernetes',
            'sql', 'nosql', 'git', 'agile', 'scrum', 'devops', 'cloud',
            'data analysis', 'deep learning', 'nlp', 'computer vision'
        ]
        skills = []
        for job in job_results.get('jobs_results', [])[:20]:
            desc = job.get('description', '').lower()
            for skill in skill_keywords:
                if skill in desc:
                    skills.append(skill)
        return [{'skill': skill, 'count': count} for skill, count in Counter(skills).most_common(15)]

# Live certification fetcher with enrollment payload
class LiveCertificationService:
    def __init__(self):
        self.coursera_api = "https://api.coursera.org/api/courses.v1"
        self.nptel_api = "https://nptel.ac.in/assets/course.json"

    def get_live_certifications(self, field, level):
        certs = []
        # Coursera
        try:
            resp = requests.get(self.coursera_api, params={
                'q': 'search',
                'query': field,
                'limit': 5
            })
            if resp.status_code == 200:
                data = resp.json()
                for course in data.get('elements', []):
                    certs.append({
                        'name': course.get('name'),
                        'platform': 'Coursera',
                        'url': f"https://www.coursera.org/learn/{course.get('slug')}",
                        'enrollment': {'platform': 'coursera', 'source_id': course.get('slug')}
                    })
        except: pass

        # NPTEL
        try:
            resp = requests.get(self.nptel_api)
            if resp.status_code == 200:
                courses = resp.json()
                for c in courses:
                    if field.lower() in c.get('discipline', '').lower():
                        certs.append({
                            'name': c.get('title'),
                            'platform': 'NPTEL',
                            'url': f"https://onlinecourses.nptel.ac.in/{c.get('id')}",
                            'enrollment': {'platform': 'nptel', 'source_id': c.get('id')}
                        })
        except: pass

        # GitHub projects
        try:
            g = Github(os.environ.get('GITHUB_TOKEN'))
            repos = g.search_repositories(f"{field} project tutorial", sort='stars', order='desc')
            for repo in repos[:5]:
                certs.append({
                    'name': f"Project: {repo.name}",
                    'platform': 'GitHub',
                    'url': repo.html_url,
                    'enrollment': {'platform': 'github', 'source_id': repo.full_name}
                })
        except: pass

        return certs

# Dynamic course builder from external sources
class DynamicCourseBuilder:
    def enroll_or_get_course(self, platform, source_id, field, level):
        course = Course.query.filter_by(source_platform=platform, source_id=str(source_id)).first()
        if course:
            return course
        if platform == 'coursera':
            course = self._create_coursera_course(source_id, field, level)
        elif platform == 'nptel':
            course = self._create_nptel_course(source_id, field, level)
        elif platform == 'github':
            course = self._create_github_course(source_id, field, level)
        else:
            return None
        if course:
            db.session.add(course)
            db.session.commit()
        return course

    def _create_coursera_course(self, slug, field, level):
        try:
            resp = requests.get(f"https://api.coursera.org/api/courses.v1?q=slug&slug={slug}")
            if resp.status_code != 200:
                return None
            elements = resp.json().get('elements', [])
            if not elements:
                return None
            info = elements[0]
            course = Course(
                title=info.get('name', slug),
                description=info.get('description', ''),
                field=field,
                difficulty_level=level,
                source_platform='coursera',
                source_id=slug,
                source_url=f"https://www.coursera.org/learn/{slug}"
            )
            # Add one generic lesson linking to Coursera
            course.lessons = [Lesson(title="Complete course on Coursera", content_type='external_link',
                                     content_url=course.source_url, order=1)]
            return course
        except Exception as e:
            print(e)
            return None

    def _create_nptel_course(self, course_id, field, level):
        try:
            resp = requests.get("https://nptel.ac.in/assets/course.json")
            if resp.status_code != 200:
                return None
            all_courses = resp.json()
            course_data = next((c for c in all_courses if c.get('id') == course_id), None)
            if not course_data:
                return None
            course = Course(
                title=course_data.get('title', 'NPTEL Course'),
                description=course_data.get('abstract', ''),
                field=field,
                difficulty_level=level,
                source_platform='nptel',
                source_id=course_id,
                source_url=f"https://onlinecourses.nptel.ac.in/{course_id}"
            )
            # Create a single external link lesson (NPTEL content requires login often)
            course.lessons = [Lesson(title="Complete NPTEL Course", content_type='external_link',
                                     content_url=course.source_url, order=1)]
            return course
        except Exception as e:
            print(e)
            return None

    def _create_github_course(self, repo_name, field, level):
        try:
            g = Github(os.environ.get('GITHUB_TOKEN'))
            repo = g.get_repo(repo_name)
            course = Course(
                title=f"Project: {repo.name}",
                description=repo.description or f"Build a project using {repo.language}",
                field=field,
                difficulty_level=level,
                source_platform='github',
                source_id=repo_name,
                source_url=repo.html_url
            )
            course.lessons = [Lesson(title="Complete the GitHub Project", content_type='external_link',
                                     content_url=repo.html_url, order=1)]
            return course
        except Exception as e:
            print(e)
            return None

# Resume template fetcher
class SupportTicket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_number = db.Column(db.String(20), unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    name = db.Column(db.String(200))
    email = db.Column(db.String(200))
    subject = db.Column(db.String(200))
    category = db.Column(db.String(50))
    message = db.Column(db.Text)
    status = db.Column(db.String(20), default='Open')
    priority = db.Column(db.String(20), default='Medium')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    admin_response = db.Column(db.Text)

class ResumeEngine:
    def get_latest_templates(self, industry):
        try:
            g = Github(os.environ.get('GITHUB_TOKEN'))
            repos = g.search_repositories(f"resume template {industry}", sort='updated', order='desc')
            templates = []
            for repo in repos[:10]:
                templates.append({
                    'name': repo.name,
                    'url': repo.html_url,
                    'stars': repo.stargazers_count,
                    'updated': repo.updated_at.isoformat()
                })
            return templates
        except:
            return []

# Instantiate services
academic_assessor = AcademicAssessor()
interview_analyzer = InterviewAnalyzer()
market_intel = MarketIntelligenceService()
cert_service = LiveCertificationService()
course_builder = DynamicCourseBuilder()
resume_engine = ResumeEngine()

# ================== ROUTES ==================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password_hash, request.form['password']):
            login_user(user)
            return redirect(url_for('dashboard'))
        return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        hashed = generate_password_hash(request.form['password'])
        user = User(
            username=request.form['username'],
            email=request.form['email'],
            password_hash=hashed,
            full_name=request.form['full_name']
        )
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/terms')
def terms():
    return render_template('terms.html', current_date=datetime.utcnow().strftime('%B %d, %Y'))

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        ticket_num = f"TKT-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        
        ticket = SupportTicket(
            ticket_number=ticket_num,
            user_id=current_user.id if current_user.is_authenticated else None,
            name=request.form.get('name'),
            email=request.form.get('email'),
            subject=request.form.get('subject'),
            category=request.form.get('category'),
            message=request.form.get('message'),
            priority=request.form.get('priority', 'Medium')
        )
        db.session.add(ticket)
        db.session.commit()
        
        return render_template('contact.html', success=True, ticket_number=ticket_num)
    
    return render_template('contact.html')

@app.route('/admin/tickets')
@login_required
def admin_tickets():
    if current_user.username != 'admin':
        return redirect(url_for('dashboard'))
    
    tickets = SupportTicket.query.order_by(SupportTicket.created_at.desc()).all()
    return render_template('admin_tickets.html', tickets=tickets)


@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/exam-mode', methods=['GET', 'POST'])
@login_required
def exam_mode():
    if request.method == 'POST':
        data = request.json
        scores = []
        for sub in data['subjects']:
            score = ExamScore(
                user_id=current_user.id,
                subject=sub['name'],
                theory_marks=sub['theory'],
                practical_marks=sub['practical'],
                understanding_level=sub['understanding'],
                semester=sub['semester']
            )
            db.session.add(score)
            scores.append(score)
        db.session.commit()
        assessment = academic_assessor.assess_professional_level(scores)
        current_user.professional_level = assessment['level']
        db.session.commit()
        study_plan = academic_assessor.generate_study_plan(scores, current_user.target_field)
        return jsonify({'assessment': assessment, 'study_plan': study_plan})
    return render_template('exam_mode.html')

@app.route('/placement-mode')
@login_required
def placement_mode():
    return render_template('placement_mode.html')

@app.route('/set-target-field', methods=['POST'])
@login_required
def set_target_field():
    current_user.target_field = request.json['field']
    db.session.commit()
    return jsonify({'success': True})

@app.route('/interview-mode')
@login_required
def interview_mode():
    return render_template('interview_mode.html')

@app.route('/analyze-interview', methods=['POST'])
@login_required
def analyze_interview():
    try:
        frame_data = request.json.get('frame')
        if not frame_data:
            return jsonify({'error': 'No frame'}), 400
        encoded = frame_data.split(',')[1]
        nparr = np.frombuffer(base64.b64decode(encoded), np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        analysis = interview_analyzer.analyze_frame(frame)
        session_entry = InterviewSession(
            user_id=current_user.id,
            posture_score=analysis['posture_score'],
            eye_contact_score=analysis['eye_contact_score'],
            body_language_score=analysis['body_language_score'],
            overall_feedback=json.dumps(analysis['feedback']),
            duration=request.json.get('duration', 0)
        )
        db.session.add(session_entry)
        db.session.commit()
        return jsonify(analysis)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/market-trends')
@login_required
def api_market_trends():
    field = request.args.get('field', current_user.target_field)
    return jsonify(market_intel.get_trending_technologies(field))

@app.route('/api/live-certifications')
@login_required
def api_live_certifications():
    field = request.args.get('field', current_user.target_field)
    level = request.args.get('level', current_user.professional_level or 1)
    return jsonify(cert_service.get_live_certifications(field, level))

@app.route('/api/resume-templates')
@login_required
def api_resume_templates():
    field = request.args.get('field', current_user.target_field)
    return jsonify(resume_engine.get_latest_templates(field))

@app.route('/api/job-listings')
@login_required
def api_job_listings():
    field = request.args.get('field', current_user.target_field)
    try:
        params = {
            "engine": "google_jobs",
            "q": f"{field} jobs",
            "api_key": os.environ.get('SERPAPI_KEY'),
            "location": "India"
        }
        search = GoogleSearch(params)
        results = search.get_dict()
        jobs = []
        for job in results.get('jobs_results', [])[:20]:
            jobs.append({
                'title': job.get('title'),
                'company': job.get('company_name'),
                'location': job.get('location'),
                'salary': job.get('detected_extensions', {}).get('salary'),
                'posted': job.get('detected_extensions', {}).get('posted_at'),
                'description': job.get('description', '')[:200] + '...',
                'url': job.get('related_links', [{}])[0].get('link', '')
            })
        return jsonify(jobs)
    except Exception as e:
        return jsonify([])

# ================== DYNAMIC COURSE ENROLLMENT ==================
@app.route('/enroll-external', methods=['POST'])
@login_required
def enroll_external():
    data = request.json
    platform = data['platform']
    source_id = data['source_id']
    field = data.get('field', current_user.target_field)
    level = data.get('level', current_user.professional_level or 1)
    course = course_builder.enroll_or_get_course(platform, source_id, field, level)
    if not course:
        return jsonify({'error': 'Could not create course'}), 400
    progress = UserCourseProgress.query.filter_by(user_id=current_user.id, course_id=course.id).first()
    if not progress:
        progress = UserCourseProgress(user_id=current_user.id, course_id=course.id)
        db.session.add(progress)
        db.session.commit()
    return jsonify({'success': True, 'redirect': url_for('view_course', course_id=course.id)})


@app.route('/course/<int:course_id>')
@login_required
def view_course(course_id):
    course = Course.query.get_or_404(course_id)
    progress = UserCourseProgress.query.filter_by(user_id=current_user.id, course_id=course_id).first()
    if not progress:
        progress = UserCourseProgress(user_id=current_user.id, course_id=course_id)
        db.session.add(progress)
        db.session.commit()
    completed_lessons = json.loads(progress.completed_lessons or '[]')
    return render_template('course_lesson.html', course=course, progress=progress, completed_lessons=completed_lessons)

@app.route('/lesson/complete', methods=['POST'])
@login_required
def complete_lesson():
    # Get data from form submission
    lesson_id = int(request.form.get('lesson_id'))
    course_id = int(request.form.get('course_id'))
    
    progress = UserCourseProgress.query.filter_by(
        user_id=current_user.id, course_id=course_id
    ).first()
    
    if not progress:
        return jsonify({'error': 'No progress record found'}), 400
    
    completed = json.loads(progress.completed_lessons or '[]')
    if lesson_id not in completed:
        completed.append(lesson_id)
        progress.completed_lessons = json.dumps(completed)
        progress.last_accessed = datetime.utcnow()
        
        course = Course.query.get(course_id)
        all_lessons = [l.id for l in course.lessons]
        all_done = set(all_lessons).issubset(set(completed))
        
        if all_done:
            progress.completed = True
            progress.completed_date = datetime.utcnow()
            generate_certificate(current_user, course)
        
        db.session.commit()
    
    return redirect(url_for('view_course', course_id=course_id))

@app.route('/quiz/<int:quiz_id>')
@login_required
def take_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    return render_template('quiz.html', quiz=quiz)

@app.route('/quiz/submit', methods=['POST'])
@login_required
def submit_quiz():
    data = request.json
    quiz_id = data['quiz_id']
    answers = data['answers']
    quiz = Quiz.query.get_or_404(quiz_id)
    total = len(quiz.questions)
    correct = 0
    for q in quiz.questions:
        if str(q.id) in answers and answers[str(q.id)] == q.correct_answer:
            correct += 1
    score = (correct / total) * 100 if total > 0 else 0
    progress = UserCourseProgress.query.filter_by(user_id=current_user.id, course_id=quiz.course_id).first()
    if progress:
        scores = json.loads(progress.quiz_scores or '{}')
        scores[str(quiz_id)] = score
        progress.quiz_scores = json.dumps(scores)
        if score >= quiz.passing_score:
            progress.completed = True
            progress.completed_date = datetime.utcnow()
            generate_certificate(current_user, quiz.course)
        db.session.commit()
    return jsonify({'score': score, 'passed': score >= quiz.passing_score})

@app.route('/certificate/<code>')
def view_certificate(code):
    cert = Certificate.query.filter_by(verification_code=code).first_or_404()
    return render_template('certificate.html', cert=cert)

@app.route('/download-certificate/<code>')
def download_certificate(code):
    cert = Certificate.query.filter_by(verification_code=code).first_or_404()
    pdf_buffer = io.BytesIO()
    p = canvas.Canvas(pdf_buffer, pagesize=letter)
    p.setFont("Helvetica-Bold", 30)
    p.drawCentredString(300, 600, "Certificate of Completion")
    p.setFont("Helvetica", 20)
    user = User.query.get(cert.user_id)
    course = Course.query.get(cert.course_id)
    p.drawCentredString(300, 520, f"Awarded to {user.full_name}")
    p.drawCentredString(300, 460, f"For completing: {course.title}")
    p.drawCentredString(300, 420, f"Date: {cert.issued_date.strftime('%B %d, %Y')}")
    p.drawCentredString(300, 350, f"Verification: {cert.verification_code}")
    p.showPage()
    p.save()
    pdf_buffer.seek(0)
    return send_file(pdf_buffer, as_attachment=True, download_name='certificate.pdf')

@app.route('/api/next-steps/<int:course_id>')
@login_required
def get_next_steps(course_id):
    course = Course.query.get_or_404(course_id)
    progress = UserCourseProgress.query.filter_by(user_id=current_user.id, course_id=course_id).first()
    if not progress or not progress.completed:
        return jsonify({'error': 'Course not completed'}), 400
    recs = []
    # Suggest advanced course
    advanced = Course.query.filter(Course.field == course.field,
                                   Course.difficulty_level > course.difficulty_level).first()
    if advanced:
        recs.append({'type': 'course', 'title': f'Next: {advanced.title}',
                     'description': 'Continue building your skills', 'action_url': url_for('view_course', course_id=advanced.id)})
    # Suggest trending certification
    try:
        certs = cert_service.get_live_certifications(course.field, current_user.professional_level or 2)
        if certs:
            recs.append({'type': 'certification', 'title': f'Earn: {certs[0]["name"]}',
                         'description': 'High demand in current market', 'action_url': certs[0]['url']})
    except: pass
    # Interview practice
    recs.append({'type': 'interview', 'title': 'Mock Interview',
                 'description': 'Practice with privacy-preserving AI', 'action_url': url_for('interview_mode')})
    return jsonify(recs)

def generate_certificate(user, course):
    code = hashlib.sha256(f"{user.id}{course.id}{datetime.utcnow()}".encode()).hexdigest()[:16]
    cert = Certificate(user_id=user.id, course_id=course.id, verification_code=code)
    db.session.add(cert)
    db.session.commit()

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)