<?xml version="1.0" encoding="UTF-8"?>

<xsl:stylesheet version="1.0"
                xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

<xsl:output method="html"
              doctype-system="about:legacy-compat"
              omit-xml-declaration="yes"
              encoding="UTF-8"
              indent="no" />

<!-- <xsl:import href="frontmatter.xslt" /> -->

<xsl:template match="/desc[@objtype='class']">
  <xsl:call-template name="desc_signature">
    <xsl:with-param name="n" select="desc_signature" />
  </xsl:call-template>
  <xsl:text>&#xa;&#xa;</xsl:text>

  <xsl:call-template name="desc_content">
    <xsl:with-param name="n" select="desc_content" />
  </xsl:call-template>
</xsl:template>

<xsl:template name="desc_signature">
  <xsl:param name="n" />
  <xsl:text>### </xsl:text><span class="class signature">
    <span class="annotation">
      <xsl:value-of select="$n/desc_annotation"/>
    </span>
    <xsl:text> </xsl:text>
    <xsl:if test="$n/desc_addname">
      <span class="addname">
        <xsl:value-of select="$n/desc_addname"/>
      </span>
    </xsl:if>
    <span class="name">
      <xsl:value-of select="$n/desc_name"/>
    </span>
  </span>
</xsl:template>

<xsl:template name="desc_content">
  <xsl:param name="n" />
  <xsl:for-each select="$n/desc/preceding-sibling::paragraph">
    <xsl:call-template name="paragraph"/>
  </xsl:for-each>

  <xsl:for-each select="$n/desc[@objtype='method']">
    <xsl:call-template name="method"/>
  </xsl:for-each>
</xsl:template>

<xsl:template name="paragraph">
    <xsl:value-of select="." /><xsl:text>&#xa;&#xa;</xsl:text>
</xsl:template>

<xsl:template name="method">
  <xsl:text>#### </xsl:text><span class="method signature">
    <span class="name">
      <xsl:value-of select="./desc_signature/desc_name"/>
    </span>
    <span class="parameter-list">
      <xsl:text>(</xsl:text>
        <xsl:value-of select="./desc_signature/desc_parameterlist"/>
      <xsl:text>)</xsl:text>
    </span>
    <!-- <xsl:value-of select="./desc_signature/desc_name" /><xsl:text>&#xa;&#xa;</xsl:text> -->
  </span><xsl:text>&#xa;&#xa;</xsl:text>
</xsl:template>

<!-- <xsl:template match="/desc_signature">
  <span class="class_annotation"><xsl:value-of select="desc_annotation"/></span><xsl:text> </xsl:text>
  <span class="class_module"><xsl:value-of select="desc_addname"/></span>
  <span class="class_name"><xsl:value-of select="desc_name"/></span>
</xsl:template> -->

<!-- <xsl:template match="/paragraph">
<xsl:value-of select="*"/><xsl:text>\n</xsl:text>
</xsl:template> -->

</xsl:stylesheet>
