# Copyright (c) 2012 Web Notes Technologies Pvt Ltd (http://erpnext.com)
# 
# MIT License (MIT)
# 
# Permission is hereby granted, free of charge, to any person obtaining a 
# copy of this software and associated documentation files (the "Software"), 
# to deal in the Software without restriction, including without limitation 
# the rights to use, copy, modify, merge, publish, distribute, sublicense, 
# and/or sell copies of the Software, and to permit persons to whom the 
# Software is furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in 
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, 
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A 
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT 
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF 
# CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE 
# OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
# 

"""
	DocLayer is a Single DocType used to mask the Property Setter
	Thus providing a better UI from user perspective
"""
import webnotes

class DocType:
	def __init__(self, doc, doclist=[]):
		self.doc, self.doclist = doc, doclist
		self.doctype_properties = [
			'autoname',
			'search_fields',
			'tag_fields',
			'default_print_format',
			'read_only_onload',
			'allow_print',
			'allow_email',
			'allow_copy',
			'allow_attach',
			'max_attachments' 
		]
		self.docfield_properties = [
			'idx',
			'label',
			'fieldtype',
			'fieldname',
			'options',
			'permlevel',
			'width',
			'reqd',
			'in_filter',
			'hidden',
			'print_hide',
			'report_hide',
			'allow_on_submit',
			'depends_on',
			'description',
			'default',
			'name'
		]
		self.set_true_doctype()


	def set_true_doctype(self):
		"""
			Sets a value of self.true_doctype as the actual doctype and not its label
		"""
		if self.doc.doc_type:
			from webnotes.utils import get_label_doctype
			self.true_doctype = get_label_doctype(self.doc.doc_type)
		else: self.true_doctype = None


	def get(self):
		"""
			Gets DocFields applied with Property Setter customizations via DocLayerField
		"""
		self.clear()

		if self.doc.doc_type:
			if not self.true_doctype: self.set_true_doctype()
			from webnotes.model.doc import addchild

			for d in self.get_ref_doclist():
				if d.doctype=='DocField':
					new = addchild(self.doc, 'fields', 'DocLayerField', 1, self.doclist)
					self.set(
						{
							'list': self.docfield_properties,
							'doc' : d,
							'doc_to_set': new
						}
					)
				elif d.doctype=='DocType':
					self.set({ 'list': self.doctype_properties, 'doc': d })


	def get_ref_doclist(self):
		"""
			* Gets doclist of type self.doc.doc_type
			* Applies property setter properties on the doclist
			* returns the modified doclist
		"""
		from webnotes.model.doctype import _DocType
		from webnotes.model.doc import get
		
		ref_doclist = get('DocType', self.true_doctype)
		_DocType(self.true_doctype)._override_field_properties(ref_doclist)
		
		return ref_doclist


	def clear(self):
		"""
			Clear fields in the doc
		"""
		# Clear table before adding new doctype's fields
		self.doc.clear_table(self.doclist, 'fields')
		self.set({ 'list': self.doctype_properties, 'value': None })
	
		
	def set(self, args):
		"""
			Set a list of attributes of a doc to a value
			or to attribute values of a doc passed
			
			args can contain:
			* list --> list of attributes to set
			* doc_to_set --> defaults to self.doc
			* value --> to set all attributes to one value eg. None
			* doc --> copy attributes from doc to doc_to_set
		"""
		if not 'doc_to_set' in args:
			args['doc_to_set'] = self.doc

		if 'list' in args:
			if 'value' in args:
				for f in args['list']:
					args['doc_to_set'].fields[f] = None
			elif 'doc' in args:
				for f in args['list']:
					args['doc_to_set'].fields[f] = args['doc'].fields[f]
		else:
			webnotes.msgprint("Please specify args['list'] to set", raise_exception=1)


	def post(self):
		"""
			Save diff between DocLayer DocList and DocType DocList as property setter entries
		"""
		if self.doc.doc_type:
			from webnotes.model import doc
			from webnotes.model.doctype import get
			
			this_doclist = [self.doc] + self.doclist
			ref_doclist = self.get_ref_doclist()
			dt_doclist = doc.get('DocType', self.true_doctype)
			
			# get a list of property setter docs
			diff_list = self.diff(this_doclist, ref_doclist, dt_doclist)
			
			self.set_properties(diff_list)


	def diff(self, new_dl, ref_dl, dt_dl):
		"""
			Get difference between new_dl doclist and ref_dl doclist
			then check how it differs from dt_dl i.e. default doclist
		"""
		import re
		self.defaults = self.get_defaults()
		diff_list = []
		for new_d in new_dl:
			for ref_d in ref_dl:
				if ref_d.doctype == 'DocField' and new_d.name == ref_d.name:
					for prop in self.docfield_properties:
						d = self.prepare_to_set(prop, new_d, ref_d, dt_dl)
						if d: diff_list.append(d)
					break
				
				elif ref_d.doctype == 'DocType' and new_d.doctype == 'DocLayer':
					for prop in self.doctype_properties:
						d = self.prepare_to_set(prop, new_d, ref_d, dt_dl)
						if d: diff_list.append(d)
					break
		
		return diff_list


	def get_defaults(self):
		"""
			Get fieldtype and default value for properties of a field
		"""
		df_defaults = webnotes.conn.sql("""
			SELECT fieldname, fieldtype, `default`, label
			FROM `tabDocField`
			WHERE parent='DocField' or parent='DocType'""", as_dict=1)
		
		defaults = {}
		for d in df_defaults:
			defaults[d['fieldname']] = d
		defaults['idx'] = {'fieldname' : 'idx', 'fieldtype' : 'Int', 'default' : 1, 'label' : 'idx'}
		defaults['previous_field'] = {'fieldname' : 'previous_field', 'fieldtype' : 'Data', 'default' : None, 'label' : 'Previous Field'}
		return defaults


	def prepare_to_set(self, prop, new_d, ref_d, dt_doclist, delete=0):
		"""
			Prepares docs of property setter
			sets delete property if it is required to be deleted
		"""
		# Check if property has changed compared to when it was loaded 
		if new_d.fields[prop] != ref_d.fields[prop] \
		and not \
		( \
			new_d.fields[prop] in [None, 0] \
			and ref_d.fields[prop] in [None, 0] \
		) and not \
		( \
			new_d.fields[prop] in [None, ''] \
			and ref_d.fields[prop] in [None, ''] \
		):
			#webnotes.msgprint("new: " + str(new_d.fields[prop]) + " | old: " + str(ref_d.fields[prop]))
			# Check if the new property is same as that in original doctype
			# If yes, we need to delete the property setter entry
			for dt_d in dt_doclist:
				if dt_d.name == ref_d.name \
				and (new_d.fields[prop] == dt_d.fields[prop] \
				or \
				( \
					new_d.fields[prop] in [None, 0] \
					and dt_d.fields[prop] in [None, 0] \
				) or \
				( \
					new_d.fields[prop] in [None, ''] \
					and dt_d.fields[prop] in [None, ''] \
				)):
					delete = 1
					break
		
			value = new_d.fields[prop]

			if prop == 'idx':
				if value > 1:
					for idoc in ([self.doc] + self.doclist):
							if idoc.fields[prop] == (value - 1):
								prop = 'previous_field'
								value = idoc.name
								break
				elif value == 1:
					prop = 'previous_field'
					value = None

			# If the above conditions are fulfilled,
			# create a property setter doc, but dont save it yet.
			from webnotes.model.doc import Document
			d = Document('Property Setter')
			d.doctype_or_field = ref_d.doctype=='DocField' and 'DocField' or 'DocType'
			d.doc_type = self.true_doctype
			d.doc_name = ref_d.name
			d.property = prop
			d.value = value
			d.property_type = self.defaults[prop]['fieldtype']
			d.default_value = self.defaults[prop]['default']
			d.select_doctype = self.doc.doc_type
			d.select_item = ref_d.label and str(ref_d.idx) \
				+ " - " + str(ref_d.label) \
				+	" (" + str(ref_d.fieldtype) + ")" \
				or None
			d.select_property = self.defaults[prop]['label']
			if delete: d.delete = 1
			
			if d.select_item:
				d.select_item = self.remove_forbidden(d.select_item)
			
			# return the property setter doc
			return d

		else: return None


	def set_properties(self, ps_doclist):
		"""
			* Delete a property setter entry
				+ if it already exists
				+ if marked for deletion
			* Save the property setter doc in the list
		"""
		for d in ps_doclist:
			# Check if the property setter doc already exists
			res = webnotes.conn.sql("""
				SELECT * FROM `tabProperty Setter`
				WHERE doc_type = %(doc_type)s
				AND doc_name = %(doc_name)s
				AND property = %(property)s""", d.fields)

			if res and res[0][0]:
				webnotes.conn.sql("""
					DELETE FROM `tabProperty Setter`
					WHERE doc_type = %(doc_type)s
					AND doc_name = %(doc_name)s
					AND property = %(property)s""", d.fields)

			# Save the property setter doc if not marked for deletion i.e. delete=0
			if not d.delete:
				d.save(1)

	
	def delete(self):
		"""
			Deletes all property setter entries for the selected doctype
			and resets it to standard
		"""
		if self.doc.doc_type:
			webnotes.conn.sql("""
				DELETE FROM `tabProperty Setter`
				WHERE doc_type = %s""", self.true_doctype)
		self.get()

	def remove_forbidden(self, string):
		"""
			Replace forbidden characters with a space
		"""
		forbidden = ['%', "'", '"', '#', '*', '?', '`']
		for f in forbidden:
			string.replace(f, ' ')


	def get_doctype_list(self):
		"""
			Returns a list of doctypes allowed to be customized
		"""
		res = webnotes.conn.sql("""\
			SELECT name FROM `tabDocType`
			WHERE (module IN 
			("Accounts", "Buying", "HR", "Knowledge Base", "Production", "Projects", 
			"Selling", "Stock", "Support") OR name IN ("Contact", "Address")) 
			AND IFNULL(issingle, 0)=0 AND IFNULL(in_create, 0)=0
		""")

		from webnotes.utils import get_doctype_label
		dt_label_dict = get_doctype_label()
	
		doctype_list = res and [dt_label_dict.get(r[0], r[0]) for r in res] or []
		doctype_list.sort()
	
		return {'doctype_list': doctype_list}
