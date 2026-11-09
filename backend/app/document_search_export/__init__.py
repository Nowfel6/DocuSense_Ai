"""Document search and governed export API/domain boundaries.

Modules use ordinary package-relative imports. The host application must supply
concrete database, embedding, authentication, rate-limit, queue, storage, worker,
and expiry-reconciliation dependencies explicitly.
"""
