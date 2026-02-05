import sqlite3
import hashlib

# Connect to database
conn = sqlite3.connect('collective_intelligence.db')
cursor = conn.cursor()

# Create admin account
username = 'admin'
password = 'admin123'
email = 'admin@platform.com'
password_hash = hashlib.sha256(password.encode()).hexdigest()

# Insert or replace admin user
cursor.execute('''
    INSERT OR REPLACE INTO users (id, username, email, password_hash, role, created_at)
    VALUES (1, ?, ?, ?, 'admin', CURRENT_TIMESTAMP)
''', (username, email, password_hash))

conn.commit()
conn.close()

print('✓ Admin account created successfully!')
print(f'  Username: {username}')
print(f'  Password: {password}')
print(f'  Access at: http://localhost:5000/admin/login')
