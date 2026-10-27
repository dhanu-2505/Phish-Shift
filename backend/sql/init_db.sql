CREATE TABLE IF NOT EXISTS `scan_results` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `message_text` LONGTEXT NOT NULL,
    `predicted_label` VARCHAR(32) NOT NULL,
    `risk_score` DECIMAL(6, 5) NOT NULL,
    `explanation` TEXT NOT NULL,
    `record_kind` VARCHAR(16) NOT NULL DEFAULT 'user',
    `created_at` TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (`id`),
    KEY `idx_scan_results_created_at` (`created_at`),
    KEY `idx_scan_results_predicted_label` (`predicted_label`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `model_evaluations` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `model_name` VARCHAR(100) NOT NULL,
    `model_version` VARCHAR(100) NOT NULL,
    `dataset_name` VARCHAR(255) NOT NULL,
    `dataset_version` VARCHAR(100) NULL,
    `dataset_source` TEXT NOT NULL,
    `precision_score` DECIMAL(7, 6) NOT NULL,
    `recall_score` DECIMAL(7, 6) NOT NULL,
    `f1_score` DECIMAL(7, 6) NOT NULL,
    `false_positive_rate` DECIMAL(7, 6) NOT NULL,
    `evaluated_at` TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (`id`),
    KEY `idx_model_evaluations_name_version` (`model_name`, `model_version`),
    KEY `idx_model_evaluations_evaluated_at` (`evaluated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `model_versions` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `model_name` VARCHAR(100) NOT NULL,
    `model_version` VARCHAR(100) NOT NULL,
    `artifact_path` VARCHAR(1024) NOT NULL,
    `training_dataset_name` VARCHAR(255) NOT NULL,
    `training_dataset_version` VARCHAR(100) NULL,
    `training_dataset_source` TEXT NOT NULL,
    `created_at` TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_model_versions_name_version` (`model_name`, `model_version`),
    KEY `idx_model_versions_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
