COPY (
    SELECT * FROM read_json({{source}}, format = 'newline_delimited', columns = {{columns}})
) TO {{target}} (FORMAT parquet);
