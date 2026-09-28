-- 合成查询，未执行。cleaned 为待准备的清洗结果表。
SELECT campaign, SUM(clicks)*1.0/NULLIF(SUM(views),0) AS ctr
FROM cleaned GROUP BY campaign;
