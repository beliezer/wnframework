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
 DocType module
 ==============
 
 This module has the DocType class that represents a "DocType" as metadata.
 This is usually called by the form builder or report builder.

 Key functions:
	* manage cache - read / write
	* merge client-side scripts
	* update properties from the modules .txt files

 Cache management:
	* Cache is stored in __DocTypeCache
"""

import webnotes
import webnotes.model
import webnotes.model.doclist
import webnotes.model.doc

from webnotes.utils import cstr, cint

class _DocType:
	"""
	   The _DocType object is created internally using the module's `get` method.
	"""
	def __init__(self, name):
		self.name = name
	
	# is cache modified ?
	# =================================================================
	
	def is_modified(self):
		"""
			Returns true if modified
		"""		
		try:
			# doctype modified
			modified = webnotes.conn.sql("select modified from tabDocType where name=%s", self.name)[0][0]
	
			# cache modified
			cache_modified = webnotes.conn.sql("SELECT modified from `__DocTypeCache` where name='%s'" % self.name)[0][0]
			
		except IndexError, e:
			return 1

		return cache_modified != modified

	# write to cache
	# =================================================================

	def _update_cache(self, doclist):
		import zlib

		if webnotes.conn.sql("SELECT name FROM __DocTypeCache WHERE name=%s", self.name):
			webnotes.conn.sql("UPDATE `__DocTypeCache` SET `modified`=%s, `content`=%s WHERE name=%s", (doclist[0].modified, zlib.compress(str([d.fields for d in doclist]),2), self.name))
		else:
			webnotes.conn.sql("INSERT INTO `__DocTypeCache` (`name`, `modified`, `content`) VALUES (%s, %s, %s)" , (self.name, doclist[0].modified, zlib.compress(str([d.fields for d in doclist]))))

	# read from cache
	# =================================================================

	def _load_from_cache(self):
		import zlib
	
		doclist = eval(zlib.decompress(webnotes.conn.sql("SELECT content from `__DocTypeCache` where name=%s", self.name)[0][0]))
		return [webnotes.model.doc.Document(fielddata = d) for d in doclist]


	# load options for "link:" type 'Select' fields
	# =================================================================
			
	def _load_select_options(self, doclist):
		for d in doclist:
			if d.doctype=='DocField' and d.fieldtype=='Select' and d.options and d.options[:5].lower()=='link:':
				op = d.options.split('\n')
				if len(op)>1 and op[1][:4].lower() == 'sql:':
					ol = webnotes.conn.sql(op[1][4:].replace('__user', webnotes.session['user']))	
				else:
					t = op[0][5:].strip()
					op = op[1:]
					op = [oc.replace('__user', webnotes.session['user']) for oc in op]
					
					try:
						# select options will always come from the user db
						ol = webnotes.conn.sql("select name from `tab%s` where %s docstatus!=2 order by name asc" % (t, op and (' AND '.join(op) + ' AND ') or ''))
					except:
						ol = []
				ol = [''] + [o[0] or '' for o in ol]
				d.options = '\n'.join(ol)

	# clear un-necessary code from going to the client side
	# =================================================================

	def _clear_code(self, doclist):
		if self.name != 'DocType':
			if doclist[0].server_code: doclist[0].server_code = None
			if doclist[0].server_code_core: doclist[0].server_code_core = None
			if doclist[0].client_script: doclist[0].client_script = None
			if doclist[0].client_script_core: doclist[0].client_script_core = None
			doclist[0].server_code_compiled = None

	# build a list of all the records required for the DocType
	# =================================================================
	
	def _get_last_update(self, dt):
		"""
			Returns last update timestamp
		"""
		try:
			last_update = webnotes.conn.sql("select _last_update from tabDocType where name=%s", dt)[0][0]
		except Exception, e:
			if e.args[0]==1054: 
				self._setup_last_update(dt)
				last_update = None
		
		return last_update

	def _setup_last_update(self, doctype):
		"""
			Adds _last_update column to tabDocType

		"""
		webnotes.conn.commit()
		webnotes.conn.sql("alter table `tabDocType` add column _last_update varchar(32)")
		webnotes.conn.begin()
		
	def _get_fields(self, file_name):
		"""
			Returns a dictionary of DocFields by fieldname or label
		"""
		try:
			txt = open(file_name, 'r').read()
		except:
			return
		from webnotes.model.utils import peval_doclist

		doclist = peval_doclist(txt)
		fields = {}
		for d in doclist:
			if d['doctype']=='DocField':
				if d.get('fieldname') or d.get('label'):
					fields[d.get('fieldname') or d.get('label')] = d
		return fields
		
	def _update_field_properties(self, doclist):
		"""
			Updates properties like description, depends on from the database based on the timestamp
			of the .txt file. Adds a column _last_updated if not exists in the database and uses
			it to update the file..
			
			This feature is built because description is changed / updated quite often and is tedious to
			write a patch every time. Can be extended to cover more updates
		"""
		
		update_fields = ('description', 'depends_on')

		from webnotes.modules import get_item_file
		from webnotes.utils import get_file_timestamp

		doc = doclist[0] # main doc
		file_name = get_item_file(doc.module, 'DocType', doc.name)
		time_stamp = get_file_timestamp(file_name)
		last_update = self._get_last_update(doc.name)
		
		# this is confusing because we are updating the fields of fields
		
		if last_update != time_stamp:

			# there are updates!
			fields = self._get_fields(file_name)
			if fields:
				for d in doclist:
				
					# for each field in teh outgoing doclist
					if d.doctype=='DocField':
						key = d.fieldname or d.label
					
						# if it has a fieldname or label
						if key and key in fields:
						
							# update the values
							for field_to_update in update_fields:
								if field_to_update in fields[key] and fields[key][field_to_update] != d.fields[field_to_update]:
									new_value = fields[key][field_to_update]
							
									# in doclist
									d.fields[field_to_update] = new_value
						
									# in database
									webnotes.conn.sql("update tabDocField set `%s` = %s where parent=%s and `%s`=%s" % \
										(field_to_update, '%s', '%s', (d.fieldname and 'fieldname' or 'label'), '%s'), \
										(new_value, doc.name, key))
					
				webnotes.conn.sql("update tabDocType set _last_update=%s where name=%s", (time_stamp, doc.name))
	
	def _override_field_properties(self, doclist):
		"""
			Override field properties that are updated by "Property Setter"
			The term "property" is used to define a fieldname of a field to avoid confusing
			terminology
		"""
		# load field properties and add them to a dictionary
		property_dict = {}
		dt = doclist[0].name
		try:
			for f in webnotes.conn.sql("select doc_name, property, property_type, value from `tabProperty Setter` where doc_type=%s", dt, as_dict=1):
				if not f['doc_name'] in property_dict:
					property_dict[f['doc_name']] = []
				property_dict[f['doc_name']].append(f)
		except Exception, e:
			if e.args[0]==1146:
				# no override table
				pass
			else: 
				raise e


		change_idx = False

		# loop over fields and override property
		for d in doclist:
			if d.doctype=='DocField' and d.name in property_dict:
				for p in property_dict[d.name]:
					if p['property_type']=='Check':
						d.fields[p['property']] = cint(p['value'])
					elif p['property']=='previous_field':
						change_idx = True
					else:
						d.fields[p['property']] = p['value']

		if change_idx: self._change_doclist_idx(doclist, property_dict)
					
		# override properties in the main doctype
		if dt in property_dict:
			for p in property_dict[dt]:
				doclist[0].fields[p['property']] = p['value']
				

	def _change_doclist_idx(self, doclist, property_dict):
		"""
			1. Select docs in doclist of type DocField
			2. Sort this doclist according to idx
			3. Extract the name of docs in a list
			4. Arrange the property_dict entries of property "previous_field"
			   and chain the set of fields according to value
			5. Move the docnames according to their previous field values
			6. Assign the new idx values to the doclist docs
		"""
		# Process doclist
		docfield_doclist = [d for d in doclist if d.doctype=='DocField']
		sorted_docfield_doclist = sorted(docfield_doclist, key=lambda df: df.idx)
		docfields = [d.name for d in sorted_docfield_doclist]
		
		# Process property_dict
		previous_field_dict = {}
		for pl in property_dict.values():
			for p in pl:
				if p['property'] == 'previous_field':
					previous_field_dict[str(p['value'])] = str(p['doc_name'])
		#webnotes.msgprint(previous_field_dict)
		#webnotes.msgprint(docfields)

		i = 0
		if 'None' in previous_field_dict:
			prev_field = 'None'
		else:
			i = i + 1
			prev_field = docfields[i]
		
		while previous_field_dict:
			get_next_docfield = 0

			if prev_field in previous_field_dict:
				this_field = previous_field_dict[prev_field]
				if (prev_field in docfields or prev_field=='None') and this_field in docfields:
					try:
						docfields.remove(this_field)
						if prev_field == 'None':
							docfields.insert(0, this_field)
						else:
							docfields.insert(docfields.index(prev_field) + 1, this_field)
					except ValueError:
						pass
				
				del previous_field_dict[prev_field]

				if this_field in previous_field_dict.keys():
					prev_field = this_field
				else:
					get_next_docfield = 1
			else:
				get_next_docfield = 1

			if get_next_docfield:
				i = i + 1
				if i>=len(docfields): break
				prev_field = docfields[i]
				vals = previous_field_dict.values()
				if prev_field in vals:
					i = i - 1
					keys = previous_field_dict.keys()
					prev_field = keys[vals.index(prev_field)]

		#webnotes.msgprint(doclist)
		for d in doclist:
			if d.doctype=='DocField':
				d.idx = docfields.index(d.name) + 1
				

	def make_doclist(self):
		"""
		      returns the :term:`doclist` for consumption by the client
		      
		      * it cleans up the server code
		      * executes all `$import` tags in client code
		      * replaces `link:` in the `Select` fields
		      * loads all related `Search Criteria`
		      * updates the cache
		"""		
		tablefields = webnotes.model.meta.get_table_fields(self.name)

		if self.is_modified():
			# yes
			doclist = webnotes.model.doc.get('DocType', self.name, 1)
			
			self._update_field_properties(doclist)
			self._override_field_properties(doclist)
			
			# table doctypes
			for t in tablefields: 
				table_doclist = webnotes.model.doc.get('DocType', t[0], 1)
				
				self._override_field_properties(table_doclist)
				doclist += table_doclist

			# don't save compiled server code

		else:
			doclist = self._load_from_cache()
		
		from webnotes.modules import Module

		doc = doclist[0]
		
		# add custom script if present
		from webnotes.model.code import get_custom_script
		custom = get_custom_script(doc.name, 'Client') or ''
		
		doc.fields['__js'] = \
			Module(doc.module).get_doc_file('doctype', doc.name, '.js').read() \
			+ '\n' + custom

		doc.fields['__css'] = \
			Module(doc.module).get_doc_file('doctype', doc.name, '.css').read()
			
		self._load_select_options(doclist)
		self._clear_code(doclist)

		return doclist

def clear_cache():
	webnotes.conn.sql("delete from __DocTypeCache")
	
def get_property(dt, property):
	"""
		get a doctype property, override it from property setter if specified
	"""
	prop = webnotes.conn.sql("""
		select value 
		from `tabProperty Setter` 
		where doc_type=%s and doc_name=%s and property=%s""", (dt, dt, property))
	if prop: 
		return prop[0][0]
	else:
		return webnotes.conn.get_value('DocType', dt, property)

def get_field_property(dt, fieldname, property):
	"""
		get a field property, override it from property setter if specified
	"""
	field = webnotes.conn.sql("""
		select name, `%s` 
		from tabDocField 
		where parent=%s and fieldname=%s""" % (property, '%s', '%s'), (dt, fieldname))
		
	prop = webnotes.conn.sql("""
		select value 
		from `tabProperty Setter` 
		where doc_type=%s and doc_name=%s and property=%s""", (dt, field[0][0], property))
	if prop: 
		return prop[0][0]
	else:
		return field[0][1]

def get(dt):
	"""
	Load "DocType" - called by form builder, report buider and from code.py (when there is no cache)
	"""
	doclist = _DocType(dt).make_doclist()
		
	return doclist
	 
