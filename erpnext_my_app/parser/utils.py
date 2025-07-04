# 定义几个常量
COMPANY_NAME_DEFAULT = "龍越商事株式会社"
WAREHOUSE_NAME_DEFAULT = "龍越仓库 - 龍越商事"
TERRITORY_DEFAULT = "Japan"


def get_carrier_code(carrier):
    carrier_map = {
        "yamato": "YAMATO",
        "sagawa": "SAGAWA",
        "upack": "JapanPost",
        "other": "Other",
        "fedex": "FedEx",
        "dhl": "DHL",
        "ups": "UPS",
        "amazon": "Amazon"
    }

    return carrier_map.get(carrier, "unknown")

def get_shipment_method(carrier):
    carrier_map = {
        "yamato": "ヤマト運輸",
        "sagawa": "佐川急便",
        "upack": "日本郵便",
        "other": "セイノースーパーエクスプレス",
        "fedex": "FedEx",
        "dhl": "DHL",
        "ups": "UPS",
        "amazon": "Amazon配送"
    }

    return carrier_map.get(carrier, "unknown")
