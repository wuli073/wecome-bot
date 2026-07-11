from __future__ import annotations

from io import BytesIO

import pytest


pytestmark = pytest.mark.asyncio


def _make_xlsx_bytes(rows: list[list[object]]) -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = 'Customers'
    for row in rows:
        worksheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


async def test_parse_csv_supports_utf8_and_utf8_bom():
    from langbot.pkg.broadcast.file_parser import parse_import_file

    plain = await parse_import_file(
        'customers.csv',
        'Customer Name,Order No\n Acme , SO-001 \n'.encode('utf-8'),
    )
    with_bom = await parse_import_file(
        'customers.csv',
        '\ufeffCustomer Name,Order No\n Acme , SO-001 \n'.encode('utf-8-sig'),
    )

    expected = {
        'file_type': 'csv',
        'worksheet_name': None,
        'headers': ['Customer Name', 'Order No'],
        'rows': [
            {
                'source_row_number': 2,
                'raw_data': {
                    'Customer Name': 'Acme',
                    'Order No': 'SO-001',
                },
            }
        ],
    }
    assert plain == expected
    assert with_bom == expected


async def test_parse_xlsx_reads_first_sheet_and_records_worksheet_name():
    from langbot.pkg.broadcast.file_parser import parse_import_file

    payload = _make_xlsx_bytes(
        [
            ['Customer Name', 'Order No'],
            ['Acme', 'SO-001'],
            ['Northwind', 'SO-002'],
        ]
    )

    parsed = await parse_import_file('customers.xlsx', payload)

    assert parsed == {
        'file_type': 'xlsx',
        'worksheet_name': 'Customers',
        'headers': ['Customer Name', 'Order No'],
        'rows': [
            {
                'source_row_number': 2,
                'raw_data': {'Customer Name': 'Acme', 'Order No': 'SO-001'},
            },
            {
                'source_row_number': 3,
                'raw_data': {'Customer Name': 'Northwind', 'Order No': 'SO-002'},
            },
        ],
    }


@pytest.mark.parametrize(
    ('file_name', 'payload', 'message'),
    [
        pytest.param(
            'customers.xls',
            b'fake',
            '不支持的文件格式，请上传 CSV 或 XLSX 文件',
            id='unsupported_extension',
        ),
        pytest.param(
            'customers.csv',
            b'',
            '导入文件为空，请检查文件内容',
            id='empty_file',
        ),
        pytest.param(
            'customers.csv',
            b'a' * (10 * 1024 * 1024 + 1),
            '文件大小超过限制，请上传 10MB 以内的文件',
            id='file_too_large',
        ),
    ],
)
async def test_parse_import_file_rejects_basic_invalid_inputs(file_name: str, payload: bytes, message: str):
    from langbot.pkg.broadcast.file_parser import BroadcastFileParserError, parse_import_file

    with pytest.raises(BroadcastFileParserError) as exc_info:
        await parse_import_file(file_name, payload)

    assert exc_info.value.message == message


async def test_parse_import_file_rejects_row_count_over_limit():
    from langbot.pkg.broadcast.file_parser import BroadcastFileParserError, parse_import_file

    rows = ['Customer Name,Order No']
    rows.extend([f'Customer {index},SO-{index:05d}' for index in range(1, 10002)])

    with pytest.raises(BroadcastFileParserError) as exc_info:
        await parse_import_file('customers.csv', '\n'.join(rows).encode('utf-8'))

    assert exc_info.value.message == '导入数据超过 10000 行上限，请拆分后重试'


@pytest.mark.parametrize(
    ('content', 'message'),
    [
        ('Customer Name,,Order No\nAcme,ignored,SO-001\n', '导入文件存在空字段名，请检查表头后重试'),
        ('Customer Name,Customer Name\nAcme,SO-001\n', '导入文件存在重复字段：Customer Name'),
        ('Customer Name, Customer Name \nAcme,SO-001\n', '导入文件存在重复字段：Customer Name'),
    ],
)
async def test_parse_csv_rejects_invalid_headers(content: str, message: str):
    from langbot.pkg.broadcast.file_parser import BroadcastFileParserError, parse_import_file

    with pytest.raises(BroadcastFileParserError) as exc_info:
        await parse_import_file('customers.csv', content.encode('utf-8'))

    assert exc_info.value.message == message


async def test_parse_import_file_trims_headers_skips_blank_rows_and_preserves_source_row_numbers():
    from langbot.pkg.broadcast.file_parser import parse_import_file

    parsed = await parse_import_file(
        'customers.csv',
        (
            ' Customer Name , Order No \n'
            '\n'
            ' Acme , SO-001 \n'
            ',\n'
            ' Northwind , SO-002 \n'
        ).encode('utf-8'),
    )

    assert parsed['headers'] == ['Customer Name', 'Order No']
    assert parsed['rows'] == [
        {
            'source_row_number': 3,
            'raw_data': {'Customer Name': 'Acme', 'Order No': 'SO-001'},
        },
        {
            'source_row_number': 5,
            'raw_data': {'Customer Name': 'Northwind', 'Order No': 'SO-002'},
        },
    ]


async def test_parse_xlsx_reads_plain_values_without_executing_formulas():
    from langbot.pkg.broadcast.file_parser import parse_import_file

    payload = _make_xlsx_bytes(
        [
            ['Customer Name', 'Formula'],
            ['Acme', '=SUM(1,2)'],
        ]
    )

    parsed = await parse_import_file('customers.xlsx', payload)

    assert parsed['rows'][0]['raw_data']['Formula'] == ''


async def test_parse_xlsx_rejects_corrupted_file():
    from langbot.pkg.broadcast.file_parser import BroadcastFileParserError, parse_import_file

    with pytest.raises(BroadcastFileParserError) as exc_info:
        await parse_import_file('customers.xlsx', b'not a real xlsx')

    assert exc_info.value.message == '导入文件已损坏，无法读取，请重新导出后再试'
