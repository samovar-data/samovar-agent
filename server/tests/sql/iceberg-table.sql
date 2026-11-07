-- A one-file Iceberg v2 table partitioned by dt, written with DuckDB itself (Parquet and Avro with Iceberg field ids).
-- case: data
COPY (
    SELECT DATE '2026-10-21' AS dt, visits FROM (VALUES (3::BIGINT), (5::BIGINT), (7::BIGINT)) AS v (visits)
) TO {{path}} (FORMAT parquet, FIELD_IDS {dt: 1, visits: 2});
-- case: manifest
COPY (
    SELECT 1::INTEGER AS status, 1::BIGINT AS snapshot_id, 1::BIGINT AS sequence_number,
        1::BIGINT AS file_sequence_number,
        {'content': 0::INTEGER, 'file_path': {{data}}, 'file_format': 'PARQUET',
         'partition': {'dt': DATE '2026-10-21'}, 'record_count': 3::BIGINT,
         'file_size_in_bytes': {{size}}} AS data_file
) TO {{path}} (FORMAT avro, FIELD_IDS {
    status: 0, snapshot_id: 1, sequence_number: 3, file_sequence_number: 4,
    data_file: {__duckdb_field_id: 2, content: 134, file_path: 100, file_format: 101,
        partition: {__duckdb_field_id: 102, dt: 1000}, record_count: 103, file_size_in_bytes: 104}
});
-- case: manifest list
COPY (
    SELECT {{manifest}} AS manifest_path, {{size}} AS manifest_length, 0::INTEGER AS partition_spec_id,
        0::INTEGER AS content, 1::BIGINT AS sequence_number, 1::BIGINT AS min_sequence_number,
        1::BIGINT AS added_snapshot_id, 1::INTEGER AS added_files_count, 0::INTEGER AS existing_files_count,
        0::INTEGER AS deleted_files_count, 3::BIGINT AS added_rows_count, 0::BIGINT AS existing_rows_count,
        0::BIGINT AS deleted_rows_count
) TO {{path}} (FORMAT avro, FIELD_IDS {
    manifest_path: 500, manifest_length: 501, partition_spec_id: 502, content: 517, sequence_number: 515,
    min_sequence_number: 516, added_snapshot_id: 503, added_files_count: 504, existing_files_count: 505,
    deleted_files_count: 506, added_rows_count: 512, existing_rows_count: 513, deleted_rows_count: 514
});
-- case: view
CREATE SCHEMA IF NOT EXISTS dds;
CREATE VIEW dds.{{name}} AS SELECT * FROM iceberg_scan({{metadata}});
