CREATE TEMPORARY SECRET samovar_key (
    TYPE s3, KEY_ID {{key_id}}, SECRET {{secret}},
    ENDPOINT {{endpoint}}, REGION {{region}}, URL_STYLE {{url_style}}, USE_SSL {{use_ssl}},
    SCOPE {{scope}}
);
