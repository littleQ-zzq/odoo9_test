# -*- coding: utf-8 -*-
from openerp.osv import fields, osv
from openerp.tools.translate import _
import openerp.addons.decimal_precision as dp
from datetime import datetime
from openerp import SUPERUSER_ID, api
from openerp.exceptions import except_orm, Warning, RedirectWarning

class account_invoice(osv.osv):
    _inherit = "account.invoice"
    _columns = {
        'contract_id':fields.many2one('market.contract',string='总包合同'),
        'labor_contract_id':fields.many2one('labor.contract',string='分包合同'),

    }

class account_payment(osv.osv):
    _inherit = 'account.payment'

    
    _columns = {
        'actual_line':fields.one2many('payment.actual.line','account_payment_id',string=u'分包合同明细',),
        'market_actual_line':fields.one2many('market.payment.actual.line','account_payment_id',string=u'总包合同明细',),
    }

    @api.multi
    def post(self):
        for obj in self:
            all_amount = 0
            if obj.partner_type == 'supplier':
                for line in obj.actual_line:
                    all_amount += line.payment_total
            if obj.partner_type == 'customer':
                for line in obj.market_actual_line:
                    all_amount += line.payment_total
            if all_amount > obj.amount:
                raise osv.except_osv(u'警告,明细行付款金额总和比付款总额大！')
        return super(account_payment,self).post()
