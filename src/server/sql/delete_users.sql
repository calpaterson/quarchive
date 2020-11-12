-- Delete a user
--
-- NOTE: first set the `user_uuid_to_delete` variable in psql
-- \set user_uuid_to_delete ...
begin;
delete from api_keys where user_uuid = :'user_uuid_to_delete';
delete from bookmark_tags where user_uuid = :'user_uuid_to_delete';
delete from bookmarks where user_uuid = :'user_uuid_to_delete';
delete from user_emails where user_uuid = :'user_uuid_to_delete';
delete from users where user_uuid = :'user_uuid_to_delete';
commit;
