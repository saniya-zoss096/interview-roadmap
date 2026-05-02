# create_admin.py
from app import app, db, User
from werkzeug.security import generate_password_hash

with app.app_context():
    # Check if admin already exists
    existing_admin = User.query.filter_by(username='admin').first()
    
    if existing_admin:
        print("Admin account already exists!")
        print(f"Username: {existing_admin.username}")
    else:
        admin = User(
            username='admin',
            email='admin@interviewroadmap.com',
            password_hash=generate_password_hash('Admin@123'),
            full_name='Administrator',
            target_field='Software Development',
            professional_level=4
        )
        db.session.add(admin)
        db.session.commit()
        print("✅ Admin account created successfully!")
        print("Username: Admin")
        print("Password: adMiN@123")
        print("⚠️ Change the password after first login!")