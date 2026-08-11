-- Enable RLS (safe to run multiple times)
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_roles ENABLE ROW LEVEL SECURITY;

-- =====================================================
-- Profiles: user can read only their own profile
-- =====================================================

DROP POLICY IF EXISTS "Users can read their own profile"
ON public.profiles;

CREATE POLICY "Users can read their own profile"
ON public.profiles
FOR SELECT
TO authenticated
USING (auth.uid() = id);

-- =====================================================
-- User Roles: user can read only their own role
-- =====================================================

DROP POLICY IF EXISTS "Users can read their own role"
ON public.user_roles;

CREATE POLICY "Users can read their own role"
ON public.user_roles
FOR SELECT
TO authenticated
USING (auth.uid() = user_id);