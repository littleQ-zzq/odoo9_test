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
import openerp.addons.decimal_precision as dp
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

class EmployeeList(models.Model):
    _inherit = "hr.department"

    department_code = fields.Char(string=u"部门编号")


class RelateContract(models.Model):
    _inherit = "project.project"
    market_contract_id = fields.Many2one("market.contract",string=u"关联合同")

    @api.model
    def create(self, vals):
        res = super(RelateContract,self).create(vals)
        market_contract_id = vals.get('market_contract_id',False)
        if market_contract_id:
            contract = self.env['market.contract'].browse(market_contract_id)
            contract.write({'project_id':res.id})
        return res

    @api.multi
    def write(self, vals):
        res = super(RelateContract,self).write(vals)
        market_contract_id = vals.get('market_contract_id',False)
        if market_contract_id:
            contract = self.env['market.contract'].browse(market_contract_id)
            contract.write({'project_id':self.ids[0]})
        return res

class LaborContract(models.Model):
    _name = "labor.contract"
    _inherit = ['mail.thread','ir.needaction_mixin']
    _order = "input_date desc"

    _description = u'分包合同'

    @api.model
    def _get_default_currency(self):
        currency_id = self.env['res.currency'].search([('name', '=', 'CNY'),])
        return currency_id

    @api.model
    def _get_default_partner(self):
        users = self.env['res.users'].browse(self._uid)
        return users.company_id.partner_id.id
        
    @api.depends('labor_line',)
    def _compute_payment_lines_total(self):
        """
        Compute the amounts.
        """
        for order in self:
            payment_lines_total = 0
            for line in order.labor_line:
                payment_lines_total += line.actual_payment
            order.update({
                'payment_lines_total': payment_lines_total,
            })
            if payment_lines_total and order.contract_amount:
                if payment_lines_total > order.contract_amount:
                    raise UserError(u'付款计划总金额比合同金额大')

    @api.depends('pr_line',)
    def _compute_product_lines_total(self):
        """
        Compute the amounts.
        """
        for order in self:
            product_lines_total = 0
            for line in order.pr_line:
                product_lines_total += line.price_subtotal
            order.update({
                'product_lines_total': product_lines_total,
            })

    active = fields.Boolean(string=u"有效",default=True,)
    contract_type = fields.Selection([('purchase', u'采购合同'), ('construct', u'施工合同'),('design', u'设计合同'),],required=True,string = u'合同类型',track_visibility='onchange',)
    name = fields.Char(string=u'合同名称',required=True,track_visibility='onchange',)
    code = fields.Char(string=u'编号',track_visibility='onchange',readonly=True)
    project_id = fields.Many2one('project.project',string=u'项目名称',track_visibility='onchange',required=True)
    party_a = fields.Many2one('res.partner',string=u'甲方',domain="[('is_company', '=', True)]",default=_get_default_partner,track_visibility='onchange',)
    headparty_a = fields.Char(string=u'甲方负责人',track_visibility='onchange',)
    party_b = fields.Many2one('res.partner',string=u'乙方',required=True,domain="[('supplier', '=', True),('is_company', '=', True)]",track_visibility='onchange',)
    headparty_b = fields.Char(string=u'乙方负责人',track_visibility='onchange',)
    currency_id= fields.Many2one('res.currency',string = u'币种',default=_get_default_currency,track_visibility='onchange',)
    contract_amount = fields.Float(string=u'合同金额',required=True,track_visibility='onchange',)
    other_fees = fields.Char(string=u'其他费用',track_visibility='onchange',)
    otherfees_amount = fields.Float(string=u'其他费用总额',track_visibility='onchange',)
    retention_ratio = fields.Float(string=u'保留金比例（%）',track_visibility='onchange',)
    advance_paymentratio = fields.Float(string=u'预付款比例（%）',track_visibility='onchange',)
    advance_amount = fields.Float(string=u'预付款',track_visibility='onchange',)
    retention_amount = fields.Float(string=u'保留金',track_visibility='onchange',)
    input_person = fields.Many2one('res.users',string = u'制单人',track_visibility='onchange',)
    input_date = fields.Datetime(string = u'制单日期',track_visibility='onchange',)
    pr_line = fields.One2many('product.contract.line','pr_id',u'合同产品明细')
    labor_line = fields.One2many('labor.contract.line','labor_id',u'付款计划')
    change_line = fields.One2many('contract.change','change_id',string=u'合同变更',)
    actual_line = fields.One2many('payment.actual.line','labor_contract_id',string=u'实际付款',domain=[('account_payment_id.state','in',('posted','resconciled',))])
    invoice = fields.One2many('account.invoice','labor_contract_id',string=u'发票管理',domain=[('state','not in',('cancel','draft','profforma','profforma2'))])
    remark = fields.Text(string=u'备注',)
    state_running = fields.Selection([('running',u'执行中'),('finished',u'已完成'),('cancel',u'已取消')],string=u'执行状态', default='running', track_visibility='onchange',) # 合同通过后的状态值：
    state = fields.Selection([('before_draft',u'预合同'),('draft',u'草稿'),('confirm',u'等待经理审核'),('wait_director',u'等待boss审核'),('done',u'已通过')],string=u'状态',track_visibility='onchange',)
    wkf_logs = fields.One2many('workflow.logs', compute='_wkf_logs', string=u'审批记录',)
    con_docu = fields.One2many("ir.attachment",compute='_tech_docu',string=u"合同附件")
    payment_lines_total = fields.Monetary(compute='_compute_payment_lines_total',string='总计',digits=dp.get_precision('Account'),track_visibility='onchange',)
    product_lines_total = fields.Monetary(compute='_compute_product_lines_total',string='总计',digits=dp.get_precision('Account'),track_visibility='onchange',)
    quality_control_plan = fields.Boolean(string=u"质控计划书",default=True,)

    # @api.multi
    # def onchange_advance_paymentratio(self,advance_amount,contract_amount):
    #     advance_paymentratio = 0
    #     if advance_amount and contract_amount and contract_amount != 0:
    #         advance_paymentratio = advance_amount/contract_amount*100
    #     return {'value':{'advance_paymentratio':advance_paymentratio}}

    # @api.multi
    # def onchange_retention_ratio(self,retention_amount,contract_amount):
    #     retention_ratio = 0
    #     if retention_amount and contract_amount and contract_amount != 0:
    #         retention_ratio = retention_amount/contract_amount*100
    #     return {'value':{'retention_ratio':retention_ratio}}

    # @api.multi
    # def onchange_advance_retention_ratio_labor(self,advance_amount,retention_amount,contract_amount):
    #     retention_ratio = 0
    #     advance_paymentratio = 0
    #     if advance_amount and retention_amount and contract_amount and contract_amount != 0:
    #         retention_ratio = retention_amount/contract_amount*100
    #         advance_paymentratio = advance_amount/contract_amount*100
    #     return {'value':{'retention_ratio':retention_ratio,'advance_paymentratio':advance_paymentratio}}

    @api.model
    def create(self,vals):
        if not vals.get('code',False):
            last_name = self.env['ir.sequence'].get("labor.contract")[2:]
            employee_obj = self.env['hr.employee'].search([('user_id','=',self._uid)])
            if not employee_obj:
                warning = {
                    'title': _(u'警告!'),
                    'message': _(u'没有找到员工的相关用户！')
                }        
            department_code = employee_obj.department_id and employee_obj.department_id.department_code or 'OP'
            # contract_type = self._context.get('default_contract_type',False)
            contract_type = vals.get('contract_type',False)
            if department_code:
                if contract_type=='construct':
                    vals.update({'code':"WB-%s-2-%s"%(department_code,last_name)})
                elif contract_type=='purchase':
                    vals.update({'code':"WB-%s-3-%s"%(department_code,last_name)})
                elif contract_type=='design':
                    vals.update({'code':"WB-%s-4-%s"%(department_code,last_name)})
        return super(LaborContract, self).create(vals)

    # 合同通过后的状态值
    @api.multi
    def wkf_running_cancle(self):
        self.write({'state_running': 'cancel'})
        return True

    @api.multi
    def wkf_running_done(self):
        self.write({'state_running': 'finished'})
        return True

    #给预合同设置初始状态
    @api.model
    def default_get(self, fields):
        rec = super(LaborContract, self).default_get(fields)
        if self._context.get('change_state','') == '1':
            rec.update({'state': 'before_draft'})
        else:
            rec.update({'state': 'draft'})                
        return rec

    #ir.attachment 附件按钮
    def attachment_tree_view(self, cr, uid, ids, context):        
        domain = [
             '&', ('res_model', '=', 'labor.contract'), ('res_id', 'in', ids),
        ]
        res_id = ids and ids[0] or False
        return {
            'name': _('Documents'),
            'domain': domain,
            'res_model': 'ir.attachment',
            'type': 'ir.actions.act_window',
            'view_id': False,
            'view_mode': 'tree,form',
            'view_type': 'form',
            'limit': 80,
            'context': "{'default_res_model': '%s','default_res_id': %d}" % (self._name, res_id)
    }

    @api.multi
    def _tech_docu(self):
        cr, uid, context = self._cr, self._uid, self._context
        model = self._name
        ir_attachment_obj = self.env["ir.attachment"]
        res = {}
        for res_id in self.ids:
            attachments = ir_attachment_obj.search([('res_id','=', res_id),('res_model','=',model)])
            tech_docu = self.browse(res_id)
            attachments.write({'project_code':tech_docu.code})
            res[res_id] = attachments
        for techbid in self:
            if techbid.id:
                techbid.con_docu = res[techbid.id]

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
    def wkf_to_draft(self):
        self.write({'state': 'draft'})

        return True
        
    @api.multi
    def wkf_draft(self):
        if self.state!='before_draft':
            self.write({'state': 'draft'})
        self.env.invalidate_all()
        cr = self.env.cr
        sql_workitem = "delete from wkf_workitem where state='complete' and inst_id in (select id from wkf_instance where res_id=%s and res_type='market.contract')"
        cr.execute(sql_workitem, (self.id,))
        sql_witm_trans = "delete from wkf_witm_trans where inst_id in (select id from wkf_instance where res_id=%s and res_type='market.contract')"
        cr.execute(sql_witm_trans, (self.id,))
        return True

    @api.multi
    def wkf_confirm(self):
        self.write({'state': 'confirm'})
        return True

    @api.multi
    def wkf_director(self):
        self.write({'state': 'wait_director'})
        return True

    @api.multi
    def wkf_done(self):
        self.write({'state': 'done'})
        for obj in self:
            send_sms_to_first(self,obj.create_uid, self._description, obj.name)
            send_message_to_first(self,obj.create_uid, self._description, obj.name)
            res = []
            for line in obj.pr_line:
                line_vals = {
                    'product_id':line.product_id and line.product_id.id or False,
                    'account_analytic_id':line.product_id and line.product_id.analytic_account_id and line.product_id.analytic_account_id.id or False,
                    'name':line.name or False,
                    'product_uom':line.product_id and line.product_id.uom_po_id and line.product_id.uom_po_id.id or 1,
                    'product_qty':line.product_qty,
                    'price_unit':line.price_unit,
                    'date_planned':obj.input_date,
                }
                res.append((0,0,line_vals))
            vals = {
                'partner_id':obj.party_b and obj.party_b.id or False,
                'project_id':obj.project_id and obj.project_id.id or False,
                'origin': obj.code,
                'order_line':res,
            }
            self.env['purchase.order'].create(vals)
        return True

    @api.model
    def get_guarantee_cost(self,origin):
        res = [] 
        res1 = [] 
        res2 = []  
        for o in origin:
            contract_id  = o.get('id',False) 
            contract = self.env['labor.contract'].browse(contract_id)

            #获取该合同付款计划中所有的款项名称ID
            item_ids = []             
            plan_amount = 0
            payment_amount = 0
            for labor_line in contract.labor_line:
                if labor_line.paymentitem_id.id not in item_ids:
                    item_ids.append(labor_line.paymentitem_id.id)
                if not labor_line.paymentitem_id.is_guarantee:
                    plan_amount += labor_line.actual_payment
            for actual_line in contract.actual_line:
                if actual_line.payment_name_id.is_guarantee:
                    res.append(o)
                else:
                    if actual_line.payment_name_id.id in item_ids:
                        payment_amount += actual_line.payment_total
            if plan_amount == payment_amount:
                res1.append(o)
            else:
                res2.append(o)

        return res,res1,res2


    def search_read(self, cr, uid, domain=None, fields=None, offset=0, limit=None, order=None, context=None):

        origin = super(LaborContract, self).search_read(cr, uid, domain=domain, fields=fields, offset=offset, limit=limit, order=order, context=context)

        #抓取合同质保金记录
        contract_guarantee = context.get('contract_guarantee', None)
        res,res1,res2 = self.get_guarantee_cost(cr, uid, origin,context=context)

        if contract_guarantee == 'all_cost':
            return res
        if contract_guarantee == 'only_cost':
            return res1
        if contract_guarantee == 'less_cost':
            return res2

        wkf_filter = context.get('wkf_filter', None)
        # 抓取待我审批的记录
        if wkf_filter == 'MYTODO':
            _logger.debug('before wkf_todo_items')
            res_ids = wkf_todo_items(self, cr, uid, wkf_filter)
            _logger.debug('wkf_todo_items, res_ids:%s', res_ids)
            return [x for x in origin if x['id'] in res_ids]
        return origin





    _defaults = {
        
        'input_person': lambda self, cr, uid, ctx: uid,
        'input_date':lambda *a: time.strftime('%Y-%m-%d %H:%M:%S'),
        }


class MarketContract(models.Model):
    _name = "market.contract"
    _inherit = ['mail.thread','ir.needaction_mixin']
    _order = "input_date desc"
    _description = u"总包合同"

    @api.model
    def _get_default_currency(self):
        currency_id = self.env['res.currency'].search([('name', '=', 'CNY'),])
        return currency_id
        
    @api.model
    def _get_default_partner(self):
        users = self.env['res.users'].browse(self._uid)
        return users.company_id.partner_id.id

    @api.depends('market_labor_line',)
    def _compute_gathering_lines_total(self):
        """
        Compute the amounts.
        """
        for order in self:
            gathering_lines_total = 0
            for line in order.market_labor_line:
                gathering_lines_total += line.actual_payment
            order.update({
                'gathering_lines_total': gathering_lines_total,
            })
            if gathering_lines_total and order.now_amount:
                if gathering_lines_total > order.now_amount:
                    raise UserError(u'收款计划总金额比合同金额大')

    @api.depends('market_pr_line',)
    def _compute_product_lines_total(self):
        """
        Compute the amounts.
        """
        for order in self:
            product_lines_total = 0
            for line in order.market_pr_line:
                product_lines_total += line.price_subtotal
            order.update({
                'product_lines_total': product_lines_total,
            })

    active = fields.Boolean(string=u"有效",default=True,)
    name = fields.Char(string=u'合同名称',required=True,track_visibility='onchange',)
    code = fields.Char(string=u'编号',track_visibility='onchange',readonly=True,)
    project_id = fields.Many2one('project.project',string=u'项目名称',track_visibility='onchange',)
    party_a = fields.Many2one('res.partner',string=u'甲方',required=True,domain="[('customer', '=', True), ('is_company', '=', True)]",track_visibility='onchange',)
    headparty_a = fields.Char(string=u'甲方负责人',track_visibility='onchange',)
    party_b = fields.Many2one('res.partner',string=u'乙方',default=_get_default_partner,domain="[('is_company', '=', True)]",track_visibility='onchange',)
    headparty_b = fields.Char(string=u'乙方负责人',track_visibility='onchange',)
    currency_id= fields.Many2one('res.currency',string = u'币种',default=_get_default_currency,track_visibility='onchange',)
    contract_amount = fields.Float(string=u'合同金额',required=True,track_visibility='onchange',)
    now_amount = fields.Float(string=u'现合同金额',track_visibility='onchange',)
    other_fees = fields.Char(string=u'其他费用',track_visibility='onchange',)
    otherfees_amount = fields.Float(string=u'其他费用总额',track_visibility='onchange',)
    retention_ratio = fields.Float(string=u'保留金比例（%）',track_visibility='onchange',)
    advance_paymentratio = fields.Float(string=u'预收款比例（%）',track_visibility='onchange',)
    advance_amount = fields.Float(string=u'预收款',track_visibility='onchange',)
    retention_amount = fields.Float(string=u'保留金',track_visibility='onchange',)
    input_person = fields.Many2one('res.users',string = u'制单人',track_visibility='onchange',)
    input_date = fields.Datetime(string = u'制单日期',track_visibility='onchange',)
    market_pr_line = fields.One2many('product.contract.line','market_pr_id',u'合同产品明细')
    market_labor_line = fields.One2many('market.contract.line','market_labor_id',u'收款计划')
    market_change_line = fields.One2many('market.contract.change','market_contract_id',string=u'合同变更',domain=[('state','=','done')],)
    actual_line = fields.One2many('market.payment.actual.line','market_contract_id',string=u'实际收款',domain=[('account_payment_id.state','in',('posted','resconciled',))])
    remark = fields.Text(string=u'备注',)
    invoice = fields.One2many('account.invoice','contract_id',string=u'发票管理',domain=[('state','not in',('cancel','draft','profforma','profforma2'))])
    state = fields.Selection([('draft',u'草稿'),('confirm',u'等待各部门审核'),('done',u'已通过'),('reject',u'拒绝')],string=u'状态',track_visibility='onchange',)
    wkf_logs = fields.One2many('workflow.logs', compute='_wkf_logs', string=u'审批记录',)
    scon_docu = fields.One2many("ir.attachment",compute='_tech_docu',string=u"合同附件")
    state_running = fields.Selection([('running',u'执行中'),('finished',u'已完成'),('cancel',u'已取消')],string=u'执行状态',default='running',track_visibility='onchange',) # 合同通过后的状态值：
    product_lines_total = fields.Monetary(compute='_compute_product_lines_total',string='总计',digits=dp.get_precision('Account'),track_visibility='onchange',)
    gathering_lines_total = fields.Monetary(compute='_compute_gathering_lines_total',string='总计',digits=dp.get_precision('Account'),track_visibility='onchange',)

    # @api.multi
    # def onchange_advance_paymentratio(self,advance_amount,now_amount):
    #     advance_paymentratio = 0
    #     if advance_amount and now_amount and now_amount != 0:
    #         advance_paymentratio = advance_amount/now_amount*100
    #     return {'value':{'advance_paymentratio':advance_paymentratio}}

    # @api.multi
    # def onchange_retention_ratio(self,retention_amount,now_amount):
    #     retention_ratio = 0
    #     if retention_amount and now_amount and now_amount != 0:
    #         retention_ratio = retention_amount/now_amount*100
    #     return {'value':{'retention_ratio':retention_ratio}}
    
    # @api.multi
    # def onchange_advance_retention_ratio_commercial(self,advance_amount,retention_amount,now_amount):
    #     retention_ratio = 0
    #     advance_paymentratio = 0
    #     if advance_amount and retention_amount and now_amount and now_amount != 0:
    #         retention_ratio = retention_amount/now_amount*100
    #         advance_paymentratio = advance_amount/now_amount*100
    #     return {'value':{'retention_ratio':retention_ratio,'advance_paymentratio':advance_paymentratio}}

    @api.multi
    def onchange_contract_amount(self,contract_amount):
        res={}
        if contract_amount:
            res.update({'now_amount':contract_amount,})
                
        return {'value':res}
    # 合同通过后的状态值
    @api.multi
    def wkf_running_cancle(self):
        self.write({'state_running': 'cancel'})
        return True

    @api.multi
    def wkf_running_done(self):
        self.write({'state_running': 'finished'})
        return True
        
    def attachment_tree_view(self, cr, uid, ids, context):        #attachment    附件    对应613  attachment_tree_view   按钮
        domain = [
             '&', ('res_model', '=', 'market.contract'), ('res_id', 'in', ids),
        ]
        res_id = ids and ids[0] or False
        return {
            'name': _('Documents'),
            'domain': domain,
            'res_model': 'ir.attachment',
            'type': 'ir.actions.act_window',
            'view_id': False,
            'view_mode': 'tree,form',
            'view_type': 'form',
            'limit': 80,
            'context': "{'default_res_model': '%s','default_res_id': %d}" % (self._name, res_id)
    }

    @api.multi
    def _tech_docu(self):
        cr, uid, context = self._cr, self._uid, self._context
        model = self._name
        ir_attachment_obj = self.env["ir.attachment"]
        res = {}
        for res_id in self.ids:
            attachments = ir_attachment_obj.search([('res_id','=', res_id),('res_model','=',model)])
            tech_docu = self.browse(res_id)
            attachments.write({'project_code':tech_docu.code})
            res[res_id] = attachments
        for techbid in self:
            if techbid.id:
                techbid.scon_docu = res[techbid.id]

    def create(self, cr, uid, vals, context=None):
        if context is None:
            context = {}
        if not vals.get('code', ''):
            last_name = self.pool.get('ir.sequence').get(cr, uid, "market.contract")
            employee_ids =self.pool.get('hr.employee').search(cr, uid, [('user_id','=',uid)])
            if not employee_ids:
                warning = {
                    'title': _(u'警告!'),
                    'message': _(u'没有找到员工的相关用户！')
                }        
            employee_obj = self.pool.get('hr.employee').browse(cr, uid, employee_ids, context=context) ## in the case: if 2 employee has same a user, there are the error
            department_code = employee_obj.department_id.department_code
            if department_code:
                vals['code'] = "WB-%s-1-%s"%(department_code,last_name)
            if not department_code:
                vals['code'] = "WB-OP-1-%s"%(last_name)
        return super(MarketContract, self).create(cr, uid, vals, context=context) 

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
        sql_workitem = "delete from wkf_workitem where state='complete' and inst_id in (select id from wkf_instance where res_id=%s and res_type='market.contract')"
        cr.execute(sql_workitem, (self.id,))
        sql_witm_trans = "delete from wkf_witm_trans where inst_id in (select id from wkf_instance where res_id=%s and res_type='market.contract')"
        cr.execute(sql_witm_trans, (self.id,))
        return True

    @api.multi
    def wkf_confirm(self):
        self.write({'state': 'confirm'})
        return True

    @api.multi
    def wkf_done(self):
        for obj in self:
            send_sms_to_first(self,obj.create_uid, self._description, obj.name)
            send_message_to_first(self,obj.create_uid, self._description, obj.name)
        self.write({'state': 'done'})
        return True
        

    @api.multi
    def act_reject(self):
        self.write({'state': 'reject'})
        return True

    def search_read(self, cr, uid, domain=None, fields=None, offset=0, limit=None, order=None, context=None):

        origin = super(MarketContract, self).search_read(cr, uid, domain=domain, fields=fields, offset=offset, limit=limit, order=order, context=context)
        wkf_filter = context.get('wkf_filter', None)

        if wkf_filter == 'MYTODO':
            _logger.debug('before wkf_todo_items')
            res_ids = wkf_todo_items(self, cr, uid, wkf_filter)
            _logger.debug('wkf_todo_items, res_ids:%s', res_ids)

            return [x for x in origin if x['id'] in res_ids]

        return origin
        
    _defaults = {
        'state':'draft',
        'input_person': lambda self, cr, uid, context: uid,
        'input_date':lambda *a: time.strftime('%Y-%m-%d %H:%M:%S'), 
    }


class ProductContractLine(models.Model):
    _name = "product.contract.line"
    _description = u'合同产品明细'

    active = fields.Boolean(string=u"有效",default=True,)
    pr_id = fields.Many2one('labor.contract',string=u'产品明细',)
    market_pr_id = fields.Many2one('market.contract',string=u'产品明细',)
    product_id = fields.Many2one('product.product',string = u'产品',required=True,)
    name = fields.Text(string = u'描述',)
    product_qty = fields.Float(string = u'数量',required=True)
    price_unit = fields.Float(string = u'产品单价',required=True,)
    price_subtotal = fields.Float(compute='_compute_amount_total', string=u"小计", store=True)

    @api.depends('product_qty','price_unit')
    def _compute_amount_total(self):
        for order in self:
            price_subtotal1 = 0.0
            price_subtotal1 += order.product_qty * order.price_unit
            order.update({
                'price_subtotal': price_subtotal1
            })

    def onchange_product_id(self, cr, uid, ids, product_id, name=False, context=None):
        """
        onchange handler of product_id.
        """
        if context is None:
            context = {}
        res = {'value': {'price_unit': 0.0, 'name': name or '', 'product_uom' : False}}
        if not product_id:
            return res
        product_product = self.pool.get('product.product')
        context_partner = context.copy()
        product = product_product.browse(cr, uid, product_id, context=context_partner)
        if not name:
            dummy, name = product_product.name_get(cr, uid, product_id, context=context_partner)[0]
            if product.description_purchase:
                name += '\n' + product.description_purchase
            res['value'].update({'name': name})
        qty = 1.0
        if qty:
            res['value'].update({'product_qty': qty})
        price = product.standard_price
        res['value'].update({'price_unit': price})
        return res
    product_id_change = onchange_product_id


class LaborContractLine(models.Model):
    _name = "labor.contract.line"
    _description = u'付款计划'

    active = fields.Boolean(string=u"有效",default=True,)
    paymentitem_id = fields.Many2one('payment.item',string=u'款项名称',required=True,)
    labor_id = fields.Many2one('labor.contract',string=u'付款计划',)
    payment_condition= fields.Char(string=u'付款条件',)
    payment_date = fields.Date(string=u'应付款日期',)
    payment_ration = fields.Float(string=u'付款比例',)
    actual_payment = fields.Float(string=u'应付款金额',)

    @api.multi
    def onchange_payment_ratio(self,actual_payment):
        contract_amount = self._context.get('contract_amount',0)
        payment_ratio = 0
        if actual_payment and contract_amount and contract_amount != 0:
            payment_ratio = actual_payment/contract_amount*100
        return {'value':{'payment_ration':payment_ratio}}


class MarketContractLine(models.Model):
    _name = "market.contract.line"
    _description = u'收款计划'

    active = fields.Boolean(string=u"有效",default=True,)
    paymentitem_id = fields.Many2one('payment.item',string=u'款项名称',required=True,)
    market_labor_id = fields.Many2one('market.contract',string=u'收款计划',)
    payment_condition= fields.Char(string=u'收款条件',)
    payment_date = fields.Date(string=u'应收款日期',)
    payment_ration = fields.Float(string=u'收款比例',)
    actual_payment = fields.Float(string=u'应收款金额',)

    @api.multi
    def onchange_payment_ratio(self,actual_payment):
        now_amount = self._context.get('now_amount',0)
        payment_ratio = 0
        if actual_payment and now_amount and now_amount != 0:
            payment_ratio = actual_payment/now_amount*100
        return {'value':{'payment_ration':payment_ratio}}



class ContractChange(models.Model):
    _name = "contract.change"
    _description = u'合同变更'

    active = fields.Boolean(string=u"有效",default=True,)
    change_id = fields.Many2one('labor.contract',string=u'合同变更',)
    market_change_id = fields.Many2one('market.contract',string=u'合同变更',)
    name = fields.Char(string=u'名称',)

class MarketPaymentActualLine(models.Model):
    _name = "market.payment.actual.line"
    _description = u'总包实际收款'

    active = fields.Boolean(string=u"有效",default=True,)
    market_contract_id = fields.Many2one('market.contract',string=u'总包合同',)
    account_payment_id = fields.Many2one('account.payment',string=u'收款',)
    payment_name_id = fields.Many2one('payment.item',string=u'款项名称',required=True,)
    project_id = fields.Many2one('project.project',string=u'项目',)
    payment_total = fields.Float(string=u'收款金额',)
    contract_total = fields.Float(string=u'合同金额',)
    payment_tax = fields.Float(string=u'收款比例(%)',)

    @api.multi
    def onchange_market_contract_id(self,market_contract_id):
        res = {}
        if market_contract_id:
            market_contract = self.env['market.contract'].browse(market_contract_id)
            res = {'project_id':market_contract.project_id.id,'contract_total':market_contract.now_amount,} 
            item_ids = []
            for market_line in market_contract.market_labor_line:
                if market_line.paymentitem_id.id not in item_ids:
                    item_ids.append(market_line.paymentitem_id.id) 
            domain ={'payment_name_id': [('id','in',item_ids)]} 
            return {'value':res,'domain' : domain,}
        return {'value':res}

    @api.multi
    def onchange_payment_total(self,payment_total,contract_total):
        payment_tax = 0
        if payment_total and contract_total:
            payment_tax =  payment_total/contract_total*100
        return {'value':{'payment_tax':payment_tax}}
        
    @api.model
    def create(self, vals):
        if vals.get('payment_total',False) and vals.get('payment_total',False) > vals.get('contract_total',False):
            raise UserError(u'警告,付款金额比合同金额大!')               
        return super(MarketPaymentActualLine,self).create(vals)

    @api.multi
    def write(self, vals):
        if vals.get('payment_total',False): 
            if vals.get('contract_total',False):
                if vals.get('payment_total',False) > vals.get('contract_total',False):
                    raise UserError(u'警告,付款金额比合同金额大!')
            else:
                if vals.get('payment_total',False) > self.contract_total:
                    raise UserError(u'警告,付款金额比合同金额大!') 
        return super(MarketPaymentActualLine,self).write(vals)


class PaymentActualLine(models.Model):
    _name = "payment.actual.line"
    _description = u'分包实际付款'

    active = fields.Boolean(string=u"有效",default=True,)
    labor_contract_id = fields.Many2one('labor.contract',string=u'分包合同',)
    account_payment_id = fields.Many2one('account.payment',string=u'付款',)
    payment_name_id = fields.Many2one('payment.item',string=u'款项名称',required=True,)
    project_id = fields.Many2one('project.project',string=u'项目',)
    payment_total = fields.Float(string=u'付款金额',)
    contract_total = fields.Float(string=u'合同金额',)
    payment_tax = fields.Float(string=u'付款比例(%)',)

    @api.multi
    def onchange_labor_contract_id(self,labor_contract_id):
        res = {}
        if labor_contract_id:
            labor_contract = self.env['labor.contract'].browse(labor_contract_id)  
            res = {'project_id':labor_contract.project_id.id,
            'contract_total':labor_contract.contract_amount,} 
            item_ids = []
            for labor_line in labor_contract.labor_line:
                if labor_line.paymentitem_id.id not in item_ids:
                    item_ids.append(labor_line.paymentitem_id.id)
            domain ={'payment_name_id': [('id','in',item_ids)]} 
            return {'value':res,'domain' : domain,}
        return {'value':res}

    @api.multi
    def onchange_payment_total(self,payment_total,contract_total):
        payment_tax = 0
        if payment_total and contract_total:
            payment_tax =  payment_total/contract_total*100
        return {'value':{'payment_tax':payment_tax}}
        
    @api.model
    def create(self, vals):
        if vals.get('payment_total',False) and vals.get('payment_total',False) > vals.get('contract_total',False):
            raise UserError(u'警告,付款金额比合同金额大!')               
        return super(PaymentActualLine,self).create(vals)

    @api.multi
    def write(self, vals):
        print vals.get('payment_total',False)
        if vals.get('payment_total',False): 
            if vals.get('contract_total',False):
                if vals.get('payment_total',False) > vals.get('contract_total',False):
                    raise UserError(u'警告,付款金额比合同金额大!')
            else:
                if vals.get('payment_total',False) > self.contract_total:
                    raise UserError(u'警告,付款金额比合同金额大!') 
        print vals.get('payment_total',False)
        return super(PaymentActualLine,self).write(vals)


class PaymentItem(models.Model):
    _name = "payment.item"
    _description = u"款项名称"

    active = fields.Boolean(string=u"有效",default=True,)
    name = fields.Char(string=u"名称")
    code = fields.Char(string=u"编号")
    is_guarantee = fields.Boolean(string=u"质保金")
    
    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        context = self._context or {}
        #分包合同情况

        labor_contract_id = context.get('labor_contract_id',False)
        if labor_contract_id:
            labor_contract = self.env['labor.contract'].browse(labor_contract_id)
            item_ids = []
            for labor_line in labor_contract.labor_line:
                if labor_line.paymentitem_id.id not in item_ids:
                    item_ids.append(labor_line.paymentitem_id.id)
            item_objs = self.env['payment.item'].browse(item_ids)
            return item_objs 

        #总包合同情况         
        market_contract_id = context.get('market_contract_id',False)
        if market_contract_id:            
            market_contract = self.env['market.contract'].browse(market_contract_id)
            item_ids = []
            for market_line in market_contract.market_labor_line:
                if market_line.paymentitem_id.id not in item_ids:
                    item_ids.append(market_line.paymentitem_id.id) 
            item_objs = self.env['payment.item'].browse(item_ids)
            return item_objs
        return super(PaymentItem, self).search(args, offset, limit, order, count=count)




