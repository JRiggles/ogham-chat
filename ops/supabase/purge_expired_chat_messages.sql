create extension if not exists pg_cron with schema extensions;

-- Use a private schema so the security definer function is not exposed
-- via the Supabase Data API (PostgREST).
create schema if not exists private;

create or replace function private.purge_expired_chat_messages(
    retention interval default interval '180 days'
)
returns integer
language plpgsql
security definer
set search_path = private, public
as $$
declare
    deleted_count integer;
begin
    with deleted_rows as (
        delete from public.chat_messages
        where created_at <= timezone('utc', now()) - retention
        returning 1
    )
    select count(*) into deleted_count
    from deleted_rows;

    return deleted_count;
end;
$$;

comment on function private.purge_expired_chat_messages(interval)
is 'Deletes chat_messages rows older than the configured retention interval. '
   'Lives in private schema to avoid Data API exposure.';

-- Revoke public execute access — only the cron background worker needs it.
revoke all on function private.purge_expired_chat_messages(interval) from public;

do $$
declare
    existing_job_id bigint;
begin
    select jobid
    into existing_job_id
    from cron.job
    where jobname = 'purge-expired-chat-messages';

    if existing_job_id is not null then
        perform cron.unschedule(existing_job_id);
    end if;

    perform cron.schedule(
        'purge-expired-chat-messages',
        '5 0 * * *',
        $job$select private.purge_expired_chat_messages(interval '180 days');$job$
    );
end;
$$;
