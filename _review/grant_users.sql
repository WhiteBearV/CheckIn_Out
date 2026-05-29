-- grant_users.sql — ให้สิทธิ์ face_user เข้าถึงตาราง users
-- รัน: sudo -u postgres psql -d face_attendance -f /home/maeb/internship_work/FaceReg/grant_users.sql

GRANT SELECT, INSERT, UPDATE, DELETE ON users TO face_user;
GRANT USAGE, SELECT ON SEQUENCE users_id_seq TO face_user;
