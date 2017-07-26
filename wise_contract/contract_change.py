# -*- encoding: utf-8 -*-
import time
from openerp import models, fields, api, _
from openerp.tools.translate import _
import string
from openerp import api
from datetime import timedelta
import logging
import openerp
from openerp import SUPERUSER_ID
from openerp import tools
from openerp.modules.module import get_module_resource
from openerp.osv import fields, osv
from openerp import models, fields
from openerp.addons.wise_tools.wkf_tools import send_notice_message
from openerp.addons.wise_tools.wkf_tools import wkf_todo_items
from openerp.addons.wise_tools.wkf_tools import send_message_to_first
from openerp.addons.wise_tools.wkf_tools import send_sms_to_first
from openerp.exceptions import UserError
_logger = logging.getLogger(__name__)


class MarketContractChange(models.Model):
    _name = "market.contract.change"
    _inherit = ['mail.thread','ir.needaction_mixin']
    _order = "originator_date desc"
    _description = u'合同变更'

    @api.model
    def _get_default_currency(self):
        currency_id = self.env['res.currency'].search([('name', '=', 'CNY'),])
        return currency_id

    active = fields.Boolean(string=u"有效",default=True,)
    code = fields.Char(string=u'编号',track_visibility='onchange', readonly=True)
    name = fields.Char(string=u'名称',track_visibility='onchange',)
    market_contract_id = fields.Many2one('market.contract',string=u'总包合同',required=True,track_visibility='onchange',)
    currency_id= fields.Many2one('res.currency',string = u'币种',default=_get_default_currency,track_visibility='onchange',)
    change_amount = fields.Float(string=u'金额', track_visibility='onchange',)
    originator_id = fields.Many2one('res.users',string=u'制单人',default=lambda self: self.env.user, track_visibility='onchange',)
    originator_date = fields.Datetime(string=u"制单时间",default=time.strftime('%Y-%m-%d %H:%M:%S'),track_visibility='onchange',)
    notes = fields.Text(string=u'备注',track_visibility='onchange',)
    state = fields.Selection([('draft',u'草稿'),('confirm',u'等待各部门审核'),('dummy_sum',u'等待董事长审核'),('done',u'已通过'),('reject',u'拒绝')],string=u'状态',track_visibility='onchange',default=lambda self: self._context.get('state', 'draft'),)
    wkf_logs = fields.One2many('workflow.logs', compute='_wkf_logs', string=u'审批记录',)
    state_running = fields.Selection([('running',u'执行中'),('finished',u'已完成'),('cancel',u'已取消')],string=u'执行状态',default='running',track_visibility='onchange',) # 合同通过后的状态值
    
    @api.model
    def create(self, vals):
    	if not vals.get('code',''):
            last_name = self.env['ir.sequence'].get('market.contract.change') or ''
            contract_code = ''
            if vals.get('market_contract_id',False):               
                contract_id = vals.get('market_contract_id',False)
                contract = self.env['market.contract'].browse(contract_id)
                contract_code = contract.code
            vals['code'] = "%s%s"%(contract_code,last_name)

        result = super(MarketContractChange, self).create(vals)
        return result

    def _wkf_logs(self):
        cr, uid, context = self._cr, self._uid, self._context
        model = self._name
        wkl_logs_obj = self.env["workflow.logs"]
        res = {}
        for res_id in self.ids:
            res[res_id]= wkl_logs_obj.search([('res_id','=', res_id),('res_type','=',model)])
        for wade in self:
            if wade.id:
                wade.wkf_logs = res[wade.id]

    @api.multi
    def wkf_draft(self):
        self.write({'state': 'draft'})
        self.env.invalidate_all()
        cr = self.env.cr
        sql_workitem = "delete from wkf_workitem where state='complete' and inst_id in (select id from wkf_instance where res_id=%s and res_type='market.contract.change')"
        cr.execute(sql_workitem, (self.id,))
        sql_witm_trans = "delete from wkf_witm_trans where inst_id in (select id from wkf_instance where res_id=%s and res_type='market.contract.change')"
        cr.execute(sql_witm_trans, (self.id,))
        return True

    @api.multi
    def wkf_confirm(self):
        self.write({'state': 'confirm'})
        return True

    @api.multi
    def wkf_approve(self):
        self.write({'state': 'dummy_sum'})
        return True

    @api.multi
    def wkf_done(self):        
        for obj in self:
            send_sms_to_first(self,obj.create_uid, self._description, obj.name)
            send_message_to_first(self,obj.create_uid, self._description, obj.name)
            
            if not obj.market_contract_id:
                continue;
            market_contract_obj = self.env['market.contract'].browse(obj.market_contract_id.id)
            template = market_contract_obj.now_amount + obj.change_amount

            # advance_amount = market_contract_obj.advance_amount
            # retention_amount = market_contract_obj.retention_amount 
            # now_advance_paymentratio = advance_amount/template*100           
            # now_retention_ratio = retention_amount/template*100
            # market_contract_obj.write({'now_amount':template,
            #                            'advance_paymentratio':now_advance_paymentratio,
            #                            'retention_ratio':now_retention_ratio,
            #                            })
            obj.write({'state': 'done'})
        
    def search_read(self, cr, uid, domain=None, fields=None, offset=0, limit=None, order=None, context=None):

        origin = super(MarketContractChange, self).search_read(cr, uid, domain=domain, fields=fields, offset=offset, limit=limit, order=order, context=context)
        wkf_filter = context.get('wkf_filter', None)

        if wkf_filter == 'MYTODO':
            _logger.debug('before wkf_todo_items')
            res_ids = wkf_todo_items(self, cr, uid, wkf_filter)
            _logger.debug('wkf_todo_items, res_ids:%s', res_ids)

            return [x for x in origin if x['id'] in res_ids]

        return origin                     