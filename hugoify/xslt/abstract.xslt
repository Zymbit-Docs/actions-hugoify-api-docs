<?xml version="1.0" encoding="UTF-8"?>

<xsl:stylesheet version="1.0"
                xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

  <xsl:output method="text"
              doctype-system="about:legacy-compat"
              encoding="UTF-8"
              indent="yes" />

<xsl:template name="abstract" match="section[@id='abstract']">
<xsl:for-each select="./paragraph">
    <xsl:value-of select="text()"/>
</xsl:for-each>

</xsl:template>

</xsl:stylesheet>
