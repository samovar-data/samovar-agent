SELECT count(*) AS visits FROM dds.yandex_metrika_logs_api__visits WHERE dt >= current_date - INTERVAL 1 YEAR;
