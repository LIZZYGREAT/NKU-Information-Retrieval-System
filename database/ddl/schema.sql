-- 1. 用户信息表
-- 作用：支撑个性化查询与登录系统，充当其他业务表的被参照表
CREATE TABLE `User` (
    `user_id` INT AUTO_INCREMENT PRIMARY KEY,
    `username` VARCHAR(50) NOT NULL UNIQUE COMMENT '登录用户名',
    `email` VARCHAR(100) NOT NULL UNIQUE COMMENT '注册邮箱',
    `password_hash` VARCHAR(255) NOT NULL COMMENT '密码哈希值',
    `role` ENUM('admin', 'user') DEFAULT 'user' COMMENT '账户角色',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户信息表';

-- 2. 网页快照缓存表
-- 作用：对接爬虫的 MySQLPipeline，存储抓取的元数据与快照本地路径
CREATE TABLE `WebPageCache` (
    `page_id` INT AUTO_INCREMENT PRIMARY KEY,
    `url` VARCHAR(512) NOT NULL UNIQUE COMMENT '网页URL，设置唯一约束以支持 ON DUPLICATE KEY UPDATE',
    `title` VARCHAR(255) NOT NULL COMMENT '网页标题',
    `snapshot_path` VARCHAR(255) NOT NULL COMMENT '本地快照HTML文件相对路径',
    `tags` JSON NULL COMMENT '网页多标签',
    `crawl_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最近一次抓取时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='网页抓取元数据与快照表';

-- 3. 搜索日志表
-- 作用：记录用户查询历史，支撑大作业的“查询日志”功能，包含外键参照
CREATE TABLE `SearchLog` (
    `log_id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL COMMENT '执行搜索的用户ID',
    `query_text` VARCHAR(255) NOT NULL COMMENT '用户输入的搜索词',
    `search_type` ENUM('site', 'document', 'phrase', 'wildcard') DEFAULT 'site' COMMENT '查询类型',
    `search_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT `fk_log_user` FOREIGN KEY (`user_id`) REFERENCES `User` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户搜索日志表';

-- 4. 用户推荐偏好表
-- 作用：支撑个性化推荐，记录各类别权重，包含外键参照
CREATE TABLE `UserPreference` (
    `pref_id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL COMMENT '所属用户ID',
    `category` VARCHAR(50) NOT NULL COMMENT '偏好类别（如：新闻、教务、学术）',
    `weight` DECIMAL(5,2) DEFAULT 1.00 COMMENT '权重得分，初始为1.00',
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT `fk_pref_user` FOREIGN KEY (`user_id`) REFERENCES `User` (`user_id`) ON DELETE CASCADE,
    UNIQUE KEY `uk_user_category` (`user_id`, `category`) -- 确保单一用户在同一类别下只有一条权重记录
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户搜索与推荐偏好权重表';


CREATE TABLE `PageLinks` (
    `link_id` INT AUTO_INCREMENT PRIMARY KEY,
    `source_url` VARCHAR(512) NOT NULL COMMENT '源页面网址',
    `target_url` VARCHAR(512) NOT NULL COMMENT '目的页面网址',
    INDEX `idx_source` (`source_url`(255)),
    INDEX `idx_target` (`target_url`(255))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='网页超链接拓扑有向边表';


-- 6. 学院域名映射字典表
-- 作用：存储预设的学院名称与底层检索时需要提权的官方二级域名
CREATE TABLE `CollegeDomain` (
    `college_id` INT AUTO_INCREMENT PRIMARY KEY,
    `college_name` VARCHAR(100) NOT NULL COMMENT '学院名称',
    `domain_url` VARCHAR(255) NOT NULL COMMENT '映射二级域名',
    `category` VARCHAR(50) NOT NULL COMMENT '所属大类(如：人文社科类/理工医学类)',
    `sub_category` VARCHAR(50) NOT NULL COMMENT '细分学科群(如：信息科学群/数理群)'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学院域名字典表';

-- 7. 用户静态画像表
-- 作用：存储用户在冷启动(Onboarding)阶段填写的身份与学院归属
CREATE TABLE `UserProfile` (
    `profile_id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL UNIQUE COMMENT '外键，确保与User表1对1关联',
    `role` ENUM('本科生', '研究生', '教职工', '访客') DEFAULT '访客' COMMENT '身份角色',
    `college_id` INT NULL COMMENT '外键，关联CollegeDomain表',
    CONSTRAINT `fk_profile_user` FOREIGN KEY (`user_id`) REFERENCES `User` (`user_id`) ON DELETE CASCADE,
    CONSTRAINT `fk_profile_college` FOREIGN KEY (`college_id`) REFERENCES `CollegeDomain` (`college_id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户静态画像表';