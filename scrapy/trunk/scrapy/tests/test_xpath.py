import os
import re
import unittest

import libxml2

from scrapy.http import Response
from scrapy.xpath.selector import XPathSelector, XmlXPathSelector, HtmlXPathSelector
#from scrapy.xpath.constructors import xmlDoc_from_xml, xmlDoc_from_html
from scrapy.xpath.iterator import XMLNodeIterator

class XPathTestCase(unittest.TestCase):

    def setUp(self):
        libxml2.debugMemory(1)

    def tearDown(self):
        libxml2.cleanupParser()
        leaked_bytes = libxml2.debugMemory(0) 
        assert leaked_bytes == 0, "libxml2 memory leak detected: %d bytes" % leaked_bytes

    def test_selector_simple(self):
        """Simple selector tests"""
        body = "<p><input name='a'value='1'/><input name='b'value='2'/></p>"
        response = Response(domain="example.com", url="http://example.com", body=body)
        xpath = HtmlXPathSelector(response)

        xl = xpath.x('//input')
        self.assertEqual(2, len(xl))
        for x in xl:
            assert isinstance(x, XPathSelector)

        self.assertEqual(xpath.x('//input').extract(),
                         [x.extract() for x in xpath.x('//input')])

        self.assertEqual([x.extract() for x in xpath.x("//input[@name='a']/@name")],
                         [u'a'])
        self.assertEqual([x.extract() for x in xpath.x("number(concat(//input[@name='a']/@value, //input[@name='b']/@value))")],
                         [u'12.0'])

        self.assertEqual(xpath.x("concat('xpath', 'rules')").extract(),
                         [u'xpathrules'])
        self.assertEqual([x.extract() for x in xpath.x("concat(//input[@name='a']/@value, //input[@name='b']/@value)")],
                         [u'12'])

    def test_selector_nested(self):
        """Nested selector tests"""
        body = """<body>
                    <div class='one'>
                      <ul>
                        <li>one</li><li>two</li>
                      </ul>
                    </div>
                    <div class='two'>
                      <ul>
                        <li>four</li><li>five</li><li>six</li>
                      </ul>
                    </div>
                  </body>"""

        response = Response(domain="example.com", url="http://example.com", body=body)
        x = HtmlXPathSelector(response)

        divtwo = x.x('//div[@class="two"]')
        self.assertEqual(divtwo.x("//li").extract(),
                         ["<li>one</li>", "<li>two</li>", "<li>four</li>", "<li>five</li>", "<li>six</li>"])
        self.assertEqual(divtwo.x("./ul/li").extract(),
                         ["<li>four</li>", "<li>five</li>", "<li>six</li>"])
        self.assertEqual(divtwo.x(".//li").extract(),
                         ["<li>four</li>", "<li>five</li>", "<li>six</li>"])
        self.assertEqual(divtwo.x("./li").extract(),
                         [])

    def test_selector_re(self):
        body = """<div>Name: Mary
                    <ul>
                      <li>Name: John</li>
                      <li>Age: 10</li>
                      <li>Name: Paul</li>
                      <li>Age: 20</li>
                    </ul>
                    Age: 20
                  </div>

               """
        response = Response(domain="example.com", url="http://example.com", body=body)
        x = HtmlXPathSelector(response)

        name_re = re.compile("Name: (\w+)")
        self.assertEqual(x.x("//ul/li").re(name_re),
                         ["John", "Paul"])
        self.assertEqual(x.x("//ul/li").re("Age: (\d+)"),
                         ["10", "20"])

    def test_selector_over_text(self):
        hxs = HtmlXPathSelector(text='<root>lala</root>')
        self.assertEqual(hxs.extract(),
                         u'<html><body><root>lala</root></body></html>')

        xxs = XmlXPathSelector(text='<root>lala</root>')
        self.assertEqual(xxs.extract(),
                         u'<root>lala</root>')

        xxs = XmlXPathSelector(text='<root>lala</root>')
        self.assertEqual(xxs.x('.').extract(),
                         [u'<root>lala</root>'])


    def test_selector_namespaces_simple(self):
        body = """
        <test xmlns:somens="http://scrapy.org">
           <somens:a id="foo"/>
           <a id="bar">found</a>
        </test>
        """

        response = Response(domain="example.com", url="http://example.com", body=body)
        x = XmlXPathSelector(response)
        
        x.register_namespace("somens", "http://scrapy.org")
        self.assertEqual(x.x("//somens:a").extract(), 
                         ['<somens:a id="foo"/>'])


    def test_selector_namespaces_multiple(self):
        body = """<?xml version="1.0" encoding="UTF-8"?>
<BrowseNode xmlns="http://webservices.amazon.com/AWSECommerceService/2005-10-05"
            xmlns:b="http://somens.com"
            xmlns:p="http://www.scrapy.org/product" >
    <b:Operation>hello</b:Operation>
    <TestTag b:att="value"><Other>value</Other></TestTag>
    <p:SecondTestTag><material/><price>90</price><p:name>Dried Rose</p:name></p:SecondTestTag>
</BrowseNode>
        """
        response = Response(domain="example.com", url="http://example.com", body=body)
        x = XmlXPathSelector(response)

        x.register_namespace("xmlns", "http://webservices.amazon.com/AWSECommerceService/2005-10-05")
        x.register_namespace("p", "http://www.scrapy.org/product")
        x.register_namespace("b", "http://somens.com")
        self.assertEqual(len(x.x("//xmlns:TestTag")), 1)
        self.assertEqual(x.x("//b:Operation/text()").extract()[0], 'hello')
        self.assertEqual(x.x("//xmlns:TestTag/@b:att").extract()[0], 'value')
        self.assertEqual(x.x("//p:SecondTestTag/xmlns:price/text()").extract()[0], '90')
        self.assertEqual(x.x("//p:SecondTestTag").x("./xmlns:price/text()")[0].extract(), '90')
        self.assertEqual(x.x("//p:SecondTestTag/xmlns:material").extract()[0], '<material/>')

    def test_http_header_encoding_precedence(self):
        # u'\xa3'     = pound symbol in unicode
        # u'\xc2\xa3' = pound symbol in utf-8
        # u'\xa3'     = pound symbol in latin-1 (iso-8859-1)

        meta = u'<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">'
        head = u'<head>' + meta + u'</head>'
        body_content = u'<span id="blank">\xa3</span>'
        body = u'<body>' + body_content + u'</body>'
        html = u'<html>' + head + body + u'</html>'
        encoding = 'utf-8'
        html_utf8 = html.encode(encoding)

        headers = {'Content-Type': ['text/html; charset=utf-8']}
        response = Response(domain="example.com", url="http://example.com", headers=headers, body=html_utf8)
        x = HtmlXPathSelector(response)
        self.assertEquals(x.x("//span[@id='blank']/text()").extract(),
                          [u'\xa3'])

    def test_null_bytes(self):
        hxs = HtmlXPathSelector(text='<root>la\x00la</root>')
        self.assertEqual(hxs.extract(),
                         u'<html><body><root>lala</root></body></html>')

        xxs = XmlXPathSelector(text='<root>la\x00la</root>')
        self.assertEqual(xxs.extract(),
                         u'<root>lala</root>')

    def test_iterator(self):
        body = """<?xml version="1.0" encoding="UTF-8"?>
<products xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="someschmea.xsd">
  <product id="001">
    <type>Type 1</type>
    <name>Name 1</name>
  </product>
  <product id="002">
    <type>Type 2</type>
    <name>Name 2</name>
  </product>
</products>
        """
        response = Response(domain="example.com", url="http://example.com", body=body)
        attrs = []
        for x in XMLNodeIterator(response, 'product'):
            attrs.append((x.x("@id").extract(), x.x("name/text()").extract(), x.x("./type/text()").extract()))

        self.assertEqual(attrs, 
                         [(['001'], ['Name 1'], ['Type 1']), (['002'], ['Name 2'], ['Type 2'])])

if __name__ == "__main__":
    unittest.main()   
