# -*- coding: utf-8 -*-
from datetime import datetime
import time
import datetime
from openerp import models, fields, api, _


class ModelTest(models.Model):
    _name = "model.test"
    _inherit = ['mail.thread','ir.needaction_mixin']
    _description = u"测试模块"

    name = fields.Char(string=u"名称")
    age = fields.Char(string=u"年龄")
