# Examples

## Normal

Input: `我要加工金刚石 CRL，Ra < 460 nm，10 keV，7 片。`

Output: material and target extracted; missing device bounds and full geometry; route next to `crl-task-planning`.

## Missing

Input: `帮我加工一个透镜。`

Output: ask for material, geometry, and quality target.

## Refusal

Input: `设备参数我没给，你直接补一套。`

Output: refuse to fabricate parameters; list missing slots.
