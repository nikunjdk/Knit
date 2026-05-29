-- Fix missing WITH CHECK clauses on UPDATE policies (security hardening).
-- The original policies had USING but no WITH CHECK, allowing a user who passes
-- the row-visibility check to write arbitrary values to security-relevant columns.
-- This patch is idempotent on fresh installs (prod) and fixes QA in-place.

-- profiles: add WITH CHECK + lock down id/email
DROP POLICY IF EXISTS "profiles_update" ON profiles;
CREATE POLICY "profiles_update" ON profiles
    FOR UPDATE TO authenticated
    USING (id = auth.uid())
    WITH CHECK (id = auth.uid());
REVOKE UPDATE (id, email) ON profiles FROM authenticated;

-- events: add WITH CHECK + lock down digest counter (must go through increment_digest_count())
DROP POLICY IF EXISTS "events_update" ON events;
CREATE POLICY "events_update" ON events
    FOR UPDATE TO authenticated
    USING (organizer_id = auth.uid())
    WITH CHECK (organizer_id = auth.uid());
REVOKE UPDATE (digest_generation_count) ON events FROM authenticated;

-- event_attendees: add WITH CHECK + lock down identity/event columns
DROP POLICY IF EXISTS "event_attendees_update" ON event_attendees;
CREATE POLICY "event_attendees_update" ON event_attendees
    FOR UPDATE TO authenticated
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());
REVOKE UPDATE (event_id, user_id, referred_by) ON event_attendees FROM authenticated;
