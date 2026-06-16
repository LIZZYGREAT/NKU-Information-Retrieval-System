ALTER TABLE WebPageCache
ADD COLUMN tags JSON NULL COMMENT '网页多标签，如 college:社会学院, topic:新闻' AFTER snapshot_path;

