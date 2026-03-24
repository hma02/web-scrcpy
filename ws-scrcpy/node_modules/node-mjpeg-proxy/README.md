node-mjpeg-proxy
================

A node.js module to proxy MJPEG requests. Supports multiple client consuming a single stream. Fixes an iOS 6 issue with some MJPEG steams. **This is an improved version of *mjpeg-proxy*, this v2 does not use the buffertools dependency and uses the node buffer instead. It also supports .on() events**

Installation
------------

From npm:

``` bash
$ npm install node-mjpeg-proxy
```

From source:

``` bash
$ git clone https://github.com/jeroen13/node-mjpeg-proxy.git
$ cd node-mjpeg-proxy
$ npm install
```

Example
-------

### Example Usage

``` js
var MjpegProxy = require('node-mjpeg-proxy');
var express = require('express');
var app = express();

app.listen(8080);

// Create Proxy 
var proxy1 = new MjpegProxy('http://192.168.1.17:8082/ptz.jpg');

// Bind proxy to the webserver
app.get('/ptz.jpg', proxy1.proxyRequest);

// Events
proxy1.on('streamstart', function(data){
	console.log("streamstart - " + data);		// [Console output] streamstart - [MjpegProxy] Started streaming http://192.168.1.17:8082/ptz.jpg , users: 1
});

proxy1.on('streamstop', function(data){
	console.log("streamstop - " + data);	// [Console output] streamstop - [MjpegProxy] 0 Users, Stopping stream http://192.168.1.17:8082/ptz.jpg
});

proxy1.on('error', function(data){
	console.log("msg: " + data.msg);		// [Console output] msg: Error: connect ECONNREFUSED 192.168.1.17:8082
	console.log("url: " + data.url);		// [Console output] url: - http://192.168.1.17:8082/ptz.jpg
});

```

Here, it will create a proxy to the source video feed (`http://192.168.1.17:8082/ptz.jpg`). You can now access the feed at `http://localhost:8080/ptz.jpg`.

API
---

### MjpegProxy

``` js
var mjpegProxy = new MjpegProxy(mjpegUrl);
``` 

Returns: a `MjpegProxy` instance for the MJPEG stream at `mjpegUrl` URL.

#### Events:
``` js
// Create Proxy 
var proxy1 = new MjpegProxy('http://192.168.1.17:8082/ptz.jpg');

// Bind proxy to the webserver
app.get('/ptz.jpg', proxy1.proxyRequest);

// Events
proxy1.on('streamstart', function(data){
	console.log("streamstart - " + data);		// [Console output] streamstart - [MjpegProxy] Started streaming http://192.168.1.17:8082/ptz.jpg , users: 1
});

proxy1.on('streamstop', function(data){
	console.log("streamstop - " + data);	// [Console output] streamstop - [MjpegProxy] 0 Users, Stopping stream http://192.168.1.17:8082/ptz.jpg
});

proxy1.on('error', function(data){
	console.log("msg: " + data.msg);		// [Console output] msg: Error: connect ECONNREFUSED 192.168.1.17:8082
	console.log("url: " + data.url);		// [Console output] url: - http://192.168.1.17:8082/ptz.jpg
});
``` 


Credits
-------

Original prototype version from:
  * Georges-Etienne Legendre ([legege](https://github.com/legege))
  * Phil Rene ([philrene](http://github.com/philrene))
  * Chris Chua ([chrisirhc](http://github.com/chrisirhc))

License
-------

(The MIT License)

Copyright (C) 2020, Jeroen K.

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to permit
persons to whom the Software is furnished to do so, subject to the
following conditions:

The above copyright notice and this permission notice shall be included
in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN
NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE
USE OR OTHER DEALINGS IN THE SOFTWARE.

A different license may apply to other software included in this package, 
including libftdi and libusb. Please consult their respective license files
for the terms of their individual licenses.

