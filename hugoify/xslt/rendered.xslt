<?xml version="1.0" encoding="UTF-8"?>

<xsl:stylesheet version="1.0"
                xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns:renderer="testns"
                extension-element-prefixes="renderer">

  <xsl:output method="text"
              doctype-system="about:legacy-compat"
              omit-xml-declaration="yes"
              encoding="UTF-8"
              indent="no" />

<!-- <xsl:import href="frontmatter.xslt" /> -->

<xsl:template match="//enumerated_list">
    <xsl:for-each select="./list_item">
        <xsl:text>- </xsl:text><xsl:value-of select="./paragraph"/><xsl:text>\n</xsl:text>
    </xsl:for-each>
</xsl:template>

<xsl:template match="/paragraph">
<xsl:value-of select="*"/><xsl:text>\n</xsl:text>
</xsl:template>

</xsl:stylesheet>
