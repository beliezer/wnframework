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
Simple Caching:

Stores key-value pairs in database and enables simple caching

get_item(key).get() returns the cached value if not expired (else returns null)
get_item(key).set(interval = 60000) sets a value to cache, expiring after x seconds
get_item(key).clear() clears an old value
setup() sets up cache
"""

import webnotes

class CacheItem:
	def __init__(self, key):
		"""create a new cache"""
		self.key = key
	
	def get(self):
		"""get value"""
		try:
			return webnotes.conn.sql("select `value` from __CacheItem where `key`=%s and expires_on > NOW()", self.key)[0][0]
		except Exception:
			return None
	
	def set(self, value, interval=6000):
		"""set a new value, with interval"""
		try:
			self.clear()
			webnotes.conn.sql("""INSERT INTO 
					__CacheItem (`key`, `value`, expires_on) 
				VALUES 
					(%s, %s, addtime(now(), sec_to_time(%s)))
				""", (self.key, str(value), interval))
		except Exception, e:
			if e.args[0]==1146: 
				setup()
				self.set(value, interval)
			else: raise e
	
	def clear(self):
		"""clear the item"""
		webnotes.conn.sql("delete from __CacheItem where `key`=%s", self.key)

def setup():
	webnotes.conn.commit()
	webnotes.conn.sql("""create table __CacheItem(
		`key` VARCHAR(180) NOT NULL PRIMARY KEY,
		`value` TEXT,
		`expires_on` TIMESTAMP
		)""")
	webnotes.conn.begin()

def get_item(key):
	"""returns get CacheItem object"""
	return CacheItem(key)
	pass