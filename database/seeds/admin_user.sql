-- admin_user.sql - Crear usuario admin por defecto
-- NOTA: La password se sincroniza desde ADMIN_PASSWORD del entorno al arrancar
-- el backend via ensure_admin_user() en main.py.
-- Este seed solo inserta si no existe, el hash se actualiza en runtime.
INSERT INTO users (username, email, password_hash, role, is_active)
SELECT 'admin', 'admin@noticiando.pe',
       '$2b$12$LJ3m4ys3Lk0TSwHnbfOMiOXPm1Qlq5Gz0Y0Y0Y0Y0Y0Y0Y0Y0O',
       'admin', true
WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'admin@noticiando.pe');
