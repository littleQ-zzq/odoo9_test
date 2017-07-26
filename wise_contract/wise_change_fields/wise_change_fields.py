# -*- encoding: utf-8 -*-
import logging
from openerp import models, fields, api
from openerp.tools.translate import _
import openerp.addons.decimal_precision as dp
from datetime import datetime
from openerp.exceptions import UserError
from openerp.exceptions import except_orm, Warning, RedirectWarning

#raise UserError(u'日期输入格式有误,请按 “YYYY-MM” 格式重新输入！')
_logger = logging.getLogger(__name__)

class WiseChangeFields(models.Model):

    _name = 'wise.change.fields'
    _description = "Change Fields"

    @api.multi
    def _get_states(self, vals=False):
        res = []
        if vals:
            res.append(vals)
        return res

    _change_selection = lambda self, *args, **kwargs: self._get_states(*args, **kwargs)

    name = fields.Char(string=u"名称")
    model_id = fields.Many2one('ir.model',string=u"模型",required=True)
    line_id = fields.Integer(string=u"数据ID")
    state = fields.Char(string=u"当前状态", readonly=True)
    state1 = fields.Selection([('1',u'男'),('2',u'女')],string=u"状态",)
    change_state = fields.Selection(_change_selection,string=u"选择状态")
    active = fields.Boolean(string=u"有效",track_visibility='onchange',default=True,)

    @api.multi
    def onchange_model_id(self,model_id):
        res = {}
        cr, uid = self._cr, self._uid
        if model_id:
            models = self.env['ir.model'].search([('id','=',model_id)])
            model_name = models.model
            change_model = self.env[model_name]
            print "==============change_model==========%s=="%change_model
            model_state = change_model._columns['state']
            # sel = model_state.reify(cr,uid,change_model,model_state,context=None)
            
            sel = change_model.state.get_values(self.env)
            # sel = fields.Selection.get_values(self.env)
            print "==============sel==========%s=="%sel
            # plan_obj = self.env['labor.contract'].browse(contract_id) _columns['state1']
            res = {'state':'1234567',}

        return {'value': res}

    @api.multi
    def onchange_line_id(self,model_id,line_id):
        res = {}
        if model_id and line_id:
            models = self.env['ir.model'].search([('id','=',model_id)])
            model_name = models.model 
            change_model = self.env[model_name].browse(line_id)
            res = {'state':change_model.state}
        return {'value': res}

    @api.multi
    def send_notice_message(self,):
        pass
         



