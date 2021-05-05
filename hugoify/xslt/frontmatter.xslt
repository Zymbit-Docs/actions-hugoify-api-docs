<?xml version="1.0" encoding="UTF-8"?>

<xsl:stylesheet version="1.0"
                xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

  <xsl:output method="text"
              doctype-system="about:legacy-compat"
              encoding="UTF-8"
              indent="yes" />

<xsl:template match="/document" name="frontmatter">
---
title: <xsl:value-of select="document_title" />
description: <xsl:value-of select="section[@id='abstract']/paragraph[1]" />
lastmod:
draft: false
images: []
type: docs
layout: single
weight: 0
toc: false
---

</xsl:template>

</xsl:stylesheet>
