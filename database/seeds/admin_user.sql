-- =============================================================================
-- Noticiando.pe - Usuario administrador por defecto
-- Password: admin123 (generado con passlib bcrypt, 12 rounds)
-- 
-- PARA REGENERAR EL HASH:
--   from passlib.context import CryptContext
--   ctx = CryptContext(schemes=['bcrypt'], deprecated='auto')
--   print(ctx.hash('admin123'))
-- =============================================================================

INSERT INTO users (username, email, password_hash, role, is_active)
VALUES (
    'admin',
    'admin@noticiando.pe',
    '$2b$12$1qw7dFv88RF9F/MSidOLx.IrduEcwkn2CjMF4x9yx4v6OBl0TM/Nu',
    'admin',
    TRUE
)
ON CONFLICT (email) DO NOTHING;
