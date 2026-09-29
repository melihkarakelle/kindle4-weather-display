-- Last message a device sent back from a remote command (report?dev=&msg=).
ALTER TABLE devices ADD COLUMN report TEXT;
ALTER TABLE devices ADD COLUMN report_ts INTEGER;
