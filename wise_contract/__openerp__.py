# -*- encoding: utf-8 -*-
{
    "name": "合同模块",
    "version": "8.0.0.1",
    "description": """
    总包合同和分包合同
    """,
    "author": "OSCG",
    "website": "http://www.wisebond.net/",
    "category": "YD",
    'depends': [
        'base',
        'product',
        'purchase',
        'workflow_info',
        'wise_project',
        'sale',
        'account',
    ],
    'init_xml': [],
    'update_xml': [
        'labor_contract_sequence.xml',
        'security/ir.model.access.csv',
        'labor_contract_view.xml',
        'labor_contract_commercial_workflow_view.xml',
        'labor_contract_sub_workflow_veiw.xml',
        'invoice_view.xml',
        'contract_change_workflow.xml',
        'contract_change_view.xml',
        'labor_contract_menu_view.xml',
    ],


}
