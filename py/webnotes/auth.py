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

import webnotes
import webnotes.db
import webnotes.utils
import webnotes.profile
import webnotes.defs

# =================================================================================
# HTTPRequest
# =================================================================================

class HTTPRequest:
	def __init__(self):

		# Get Environment variables
		self.domain = webnotes.get_env_vars('HTTP_HOST')
		if self.domain and self.domain.startswith('www.'):
			self.domain = self.domain[4:]

		webnotes.remote_ip = webnotes.get_env_vars('REMOTE_ADDR')					

		# load cookies
		webnotes.cookie_manager = CookieManager()

		# set db
		self.set_db()

		# -----------------------------
		# start transaction
		webnotes.conn.begin()

		# login
		webnotes.login_manager = LoginManager()

		# start session
		webnotes.session_obj = Session()
		webnotes.session = webnotes.session_obj.data

		# check status
		if webnotes.conn.get_global("__session_status")=='stop':
			webnotes.msgprint(webnotes.conn.get_global("__session_status_message"))
			raise webnotes.SessionStopped('Session Stopped')


		# write out cookies if sid is supplied (this is a pre-logged in redirect)
		if webnotes.form_dict.get('sid'):
			webnotes.cookie_manager.set_cookies()

		# run login triggers
		if webnotes.form_dict.get('cmd')=='login':
			webnotes.login_manager.run_trigger('on_login_post_session')
			
		# load profile
		self.setup_profile()

		webnotes.conn.commit()
		# end transaction
		# -----------------------------

	# setup profile
	# -------------

	def setup_profile(self):
		webnotes.user = webnotes.profile.Profile()
		# load the profile data
		if webnotes.session['data'].get('profile'):
			webnotes.user.load_from_session(webnotes.session['data']['profile'])
		else:
			webnotes.user.load_profile()

	# set database login
	# ------------------

	def get_db_name(self):
		# highest priority if comes via form
		if webnotes.form_dict.get('ac_name'):
			db_name = webnotes.form_dict.get('ac_name')
		elif webnotes.form_dict.get('acx'):
			db_name = webnotes.form_dict.get('acx')
			
		# then from cookie
		elif webnotes.incoming_cookies.get('account_id'):
			db_name = webnotes.incoming_cookies.get('account_id')
			
		# then via defs
		elif hasattr(webnotes.defs, 'get_db_name'):
			db_name = webnotes.defs.get_db_name()
		
		# then default
		else:
			db_name = getattr(webnotes.defs,'default_db_name','')
		
		if not db_name:
			raise Exception, "Unable to resolve database name"
			
		return db_name

	def set_db(self, ac_name = None):
		"""connect to db, from ac_name or db_name"""
			
		webnotes.conn = webnotes.db.Database(user = self.get_db_name(), \
			password = getattr(webnotes.defs,'db_password', ''))

# =================================================================================
# Login Manager
# =================================================================================

class LoginManager:
	def __init__(self):
		self.cp = None
		if webnotes.form_dict.get('cmd')=='login':
			# clear cache
			from webnotes.session_cache import clear_cache
			clear_cache(webnotes.form_dict.get('usr'))				

			self.authenticate()
			self.post_login()
			webnotes.response['message'] = 'Logged In'

	# run triggers, write cookies
	# ---------------------------
	
	def post_login(self):
		self.run_trigger()
		self.validate_ip_address()
		self.validate_hour()
	
	# check password
	# --------------
	
	def authenticate(self, user=None, pwd=None):
		if not (user and pwd):	
			user, pwd = webnotes.form_dict.get('usr'), webnotes.form_dict.get('pwd')
		if not (user and pwd):
			webnotes.response['message'] = 'Incomplete Login Details'  
			raise webnotes.AuthenticationError
		# custom authentication (for single-sign on)
		self.load_control_panel()
		if hasattr(self.cp, 'authenticate'):
			self.user = self.cp.authenticate()
		
		# check the password
		if user=='Administrator':
			p = webnotes.conn.sql("""select name, first_name, last_name 
				from tabProfile where name=%s 
				and (`password`=%s OR `password`=PASSWORD(%s))""", (user, pwd, pwd), as_dict=1)
		else:
			p = webnotes.conn.sql("""select name, first_name, last_name 
				from tabProfile where name=%s 
				and (`password`=%s  OR `password`=PASSWORD(%s)) 
				and IFNULL(enabled,0)=1""", (user, pwd, pwd), as_dict=1)
		if not p:
			webnotes.response['message'] = 'Authentication Failed'
			raise webnotes.AuthenticationError
			#webnotes.msgprint('Authentication Failed',raise_exception=1)
			
		p = p[0]
		self.user = p['name']
		self.user_fullname = (p.get('first_name') and (p.get('first_name') + ' ') or '') \
			+ (p.get('last_name') or '')
	
	# triggers
	# --------
	
	def load_control_panel(self):
		import webnotes.model.code
		try:
			if not self.cp:
				self.cp = webnotes.model.code.get_obj('Control Panel')
		except Exception, e:
			webnotes.response['Control Panel Exception'] = webnotes.utils.getTraceback()
	
	# --------
	def run_trigger(self, method='on_login'):
		try:
			from startup import event_handlers
			if hasattr(event_handlers, method):
				getattr(event_handlers, method)(self)
			return
		except ImportError, e:
			webnotes.errprint(str(e))
	
		# deprecated
		self.load_control_panel()
		if self.cp and hasattr(self.cp, method):
			getattr(self.cp, method)(self)

	# ip validation
	# -------------
	
	def validate_ip_address(self):
		ip_list = webnotes.conn.get_value('Profile', self.user, 'restrict_ip', ignore=True)
		
		if not ip_list:
			return

		ip_list = ip_list.replace(",", "\n").split('\n')
		ip_list = [i.strip() for i in ip_list]

		for ip in ip_list:
			if webnotes.remote_ip.startswith(ip):
				return
			elif webnotes.form_dict.get('via_ip'):
				if webnotes.form_dict.get('via_ip').startswith(ip):
					return
				elif (hasattr(webnotes.defs, 'server_ip') and
						webnotes.form_dict.get('via_ip').startswith(webnotes.defs.server_ip)):
					return
			
		webnotes.msgprint('Not allowed from this IP Address')
		raise webnotes.AuthenticationError

	def validate_hour(self):
		"""
			check if user is logging in during restricted hours
		"""
		login_before = int(webnotes.conn.get_value('Profile', self.user, 'login_before', ignore=True) or 0)
		login_after = int(webnotes.conn.get_value('Profile', self.user, 'login_after', ignore=True) or 0)
		
		if not (login_before or login_after):
			return
			
		from webnotes.utils import now_datetime
		current_hour = int(now_datetime().strftime('%H'))
				
		if login_before and current_hour > login_before:
			webnotes.msgprint('Not allowed to login after restricted hour', raise_exception=1)

		if login_after and current_hour < login_after:
			webnotes.msgprint('Not allowed to login before restricted hour', raise_exception=1)

	# login as guest
	# --------------
	
	def login_as_guest(self):
		self.user = 'Guest'
		self.post_login()

	# Logout
	# ------
	
	def call_on_logout_event(self):
		import webnotes.model.code
		cp = webnotes.model.code.get_obj('Control Panel', 'Control Panel')
		if hasattr(cp, 'on_logout'):
			cp.on_logout(self)

	def logout(self, arg='', user=None):
		if not user: user = webnotes.session.get('user')
		self.user = user
		self.run_trigger('on_logout')
		webnotes.conn.sql('delete from tabSessions where user=%s', user)
		
# =================================================================================
# Cookie Manager
# =================================================================================

class CookieManager:
	def __init__(self):
		import Cookie
		webnotes.cookies = Cookie.SimpleCookie()
		self.get_incoming_cookies()

	# get incoming cookies
	# --------------------
	def get_incoming_cookies(self):
		import os
		cookies = {}
		if 'HTTP_COOKIE' in os.environ:
			c = os.environ['HTTP_COOKIE']
			webnotes.cookies.load(c)
			for c in webnotes.cookies.values():
				cookies[c.key] = c.value
					
		webnotes.incoming_cookies = cookies
		
	# Set cookies
	# -----------
	
	def set_cookies(self):
		if webnotes.form_dict.get('cmd')=='logout':
			webnotes.cookies['account_id'] = ''
		else:
			webnotes.cookies['account_id'] = webnotes.conn.cur_db_name
		
		if webnotes.session.get('sid'):
			webnotes.cookies['sid'] = webnotes.session['sid']

			# sid expires in 3 days
			import datetime
			expires = datetime.datetime.now() + datetime.timedelta(days=3)

			webnotes.cookies['sid']['expires'] = expires.strftime('%a, %d %b %Y %H:%M:%S')		

	# Set Remember Me
	# ---------------

	def set_remember_me(self):
		if webnotes.utils.cint(webnotes.form_dict.get('remember_me')):
			remember_days = webnotes.conn.get_value('Control Panel',None,'remember_for_days') or 7
			webnotes.cookies['remember_me'] = 1

			import datetime
			expires = datetime.datetime.now() + datetime.timedelta(days=remember_days)

			for k in webnotes.cookies.keys():
				webnotes.cookies[k]['expires'] = expires.strftime('%a, %d %b %Y %H:%M:%S')	

# =================================================================================
# Session 
# =================================================================================

class Session:
	def __init__(self, user=None):
		self.user = user
		self.sid = webnotes.form_dict.get('sid') or webnotes.incoming_cookies.get('sid')
		self.data = {'user':user,'data':{}}

		if webnotes.form_dict.get('cmd')=='login':
			self.start()
			return
			
		self.load()
	
	# start a session
	# ---------------
	def get_session_record(self):
		"""get session record, or return the standard Guest Record"""
		r = webnotes.conn.sql("""select user, sessiondata, status from 
			tabSessions where sid='%s'""" % self.sid)
		if not r:
			# return guest record if present
			self.sid = 'Guest'
			r = webnotes.conn.sql("""select user, sessiondata, status from 
				tabSessions where sid='%s'""" % self.sid)
			
		return r
	
	def load(self):
		import webnotes
		
		r = self.get_session_record()
	
		if r:
			r=r[0]
			
			# ExipredSession
			if r[2]=='Expired' and (webnotes.form_dict.get('cmd')!='resume_session'):
				if r[0]=='Guest' or (not webnotes.form_dict.get('cmd')) or webnotes.form_dict.get('cmd')=='logout':
					self.start_as_guest()
				else:
					webnotes.response['session_status'] = 'Session Expired'
					raise Exception, 'Session Expired'
			elif r[2]=='Logged Out':
				self.start_as_guest()
				# allow refresh or logout
				if webnotes.form_dict.get('cmd') and webnotes.form_dict.get('cmd')!='logout':
					webnotes.response['session_status'] = 'Logged Out'
					raise Exception, 'Logged Out'
			else:
				self.data = {'data': (r[1] and eval(r[1]) or {}), 
					'user':r[0], 'sid': self.sid}
		else:				
			self.start_as_guest()

	def start_as_guest(self):
		"""all guests share the same 'Guest' session"""
		webnotes.login_manager.login_as_guest()
		self.start()

	# start a session
	# ---------------
	def start(self):
		import os
		import webnotes
		import webnotes.utils
		
		# generate sid
		if webnotes.login_manager.user=='Guest':
			sid = 'Guest'
		else:
			sid = webnotes.utils.generate_hash()
		
		self.data['user'] = webnotes.login_manager.user
		self.data['sid'] = sid
		self.data['data']['session_ip'] = os.environ.get('REMOTE_ADDR');
		self.data['data']['tenant_id'] = webnotes.form_dict.get('tenant_id', 0)

		# get ipinfo
		if webnotes.conn.get_global('get_ip_info'):
			self.get_ipinfo()
		
		# insert session
		try:
			self.insert_session_record()
		except Exception, e:
			if e.args[0]==1054:
				self.add_status_column()
				self.insert_session_record()
			else:
				raise e

		# update profile
		webnotes.conn.sql("UPDATE tabProfile SET last_login = '%s', last_ip = '%s' where name='%s'" % (webnotes.utils.now(), webnotes.remote_ip, self.data['user']))

		# set cookies to write
		webnotes.session = self.data
		webnotes.cookie_manager.set_cookies()


	# resume session
	# --------------
	def resume(self):
		pwd = webnotes.form_dict.get('pwd')
		webnotes.login_manager.authenticate(self.data['user'], pwd)
		webnotes.conn.sql("update tabSessions set status='Active' where sid=%s", self.data['sid'])
		return 'Logged In'
	
	# update session
	# --------------
	def update(self):
		# update session
		if webnotes.session['user'] != 'Guest':
			webnotes.conn.sql("""update tabSessions set sessiondata=%s, user=%s, lastupdate=NOW() 
				where sid=%s""" , (str(self.data['data']), self.data['user'], self.data['sid']))	

			self.check_expired()

	# check expired
	# -------------
	def check_expired(self):
		"""expire non-guest sessions"""
		exp_sec = webnotes.conn.get_value('Control Panel', None, 'session_expiry') or '6:00:00'
		
		# set sessions as expired
		try:
			webnotes.conn.sql("""update tabSessions where TIMEDIFF(NOW(), lastupdate) > 
				%s and sid!='Guest' SET `status`='Expired'""", exp_sec)
		except Exception, e:
			if e.args[0]==1054:
				self.add_status_column()
		
		# clear out old sessions
		webnotes.conn.sql("""delete from tabSessions where TIMEDIFF(NOW(), lastupdate) 
			> '72:00:00' and sid!='Guest'""")

	# Get IP Info from ipinfodb.com
	# -----------------------------
	def get_ipinfo(self):
		import os
		
		try:
			import pygeoip
		except:
			return
		
		gi = pygeoip.GeoIP('data/GeoIP.dat')
		self.data['data']['ipinfo'] = {'countryName': gi.country_name_by_addr(os.environ.get('REMOTE_ADDR'))}
			
	# -----------------------------
	def insert_session_record(self):
		webnotes.conn.sql("insert into tabSessions (sessiondata, user, lastupdate, sid, status) values (%s , %s, NOW(), %s, 'Active')", (str(self.data['data']), self.data['user'], self.data['sid']))
		
