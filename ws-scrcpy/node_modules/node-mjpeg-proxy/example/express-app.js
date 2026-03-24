// Copyright (C) 2020, Jeroen K.
//
// Permission is hereby granted, free of charge, to any person obtaining a
// copy of this software and associated documentation files (the
// "Software"), to deal in the Software without restriction, including
// without limitation the rights to use, copy, modify, merge, publish,
// distribute, sublicense, and/or sell copies of the Software, and to permit
// persons to whom the Software is furnished to do so, subject to the
// following conditions:
//
// The above copyright notice and this permission notice shall be included
// in all copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
// OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
// MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN
// NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
// DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
// OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE
// USE OR OTHER DEALINGS IN THE SOFTWARE.

var MjpegProxy = require('../node-mjpeg-proxy');
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



// Create Proxy 
var proxy2 = new MjpegProxy('http://192.168.1.17:8082/bullet.jpg');

// Bind proxy to the webserver
app.get('/bullet.jpg', proxy2.proxyRequest);

// Events
proxy2.on('streamstart', function(data){
	console.log("streamstart - " + data);		// [Console output] streamstart - [MjpegProxy] Started streaming http://192.168.1.17:8082/bullet.jpg , users: 1
});

proxy2.on('streamstop', function(data){
	console.log("streamstop - " + data);	// [Console output] streamstop - [MjpegProxy] 0 Users, Stopping stream http://192.168.1.17:8082/bullet.jpg
});

proxy2.on('error', function(data){
	console.log("msg: " + data.msg);		// [Console output] msg: Error: connect ECONNREFUSED 192.168.1.17:8082
	console.log("url: " + data.url);		// [Console output] url: - http://192.168.1.17:8082/bullet.jpg
});



