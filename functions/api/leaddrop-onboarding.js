const LINKS = {'00':['https://buy.stripe.com/bJe6oJcxZ508gC47veg7e09',31],'10':['https://buy.stripe.com/eVqaEZ2Xp0JS3Pi7veg7e0a',41],'01':['https://buy.stripe.com/3cIdRb55x2S01Ha5n6g7e0b',41],'11':['https://buy.stripe.com/aFa00lapRfEMbhKbLug7e0c',51]};
const value = (item, maximum) => String(item || '').trim().replace(/\s+/g, ' ').slice(0, maximum);
const failure = (field, message) => Response.json({success:false, field, message}, {status:400});

export async function onRequestPost({request, env}) {
  if (!env.ONBOARDING_DB) return Response.json({success:false,message:'We could not save your setup. Please try again.'},{status:500});
  const origin = request.headers.get('Origin');
  if (origin && origin !== 'https://leaddrop.com.au') return new Response('Forbidden',{status:403});
  let body; try { body = await request.json(); } catch { return failure('', 'Please check your details and try again.'); }
  const name=value(body.name,100), business=value(body.business_name,160), email=value(body.email,254).toLowerCase(), phone=value(body.phone,32), area=value(body.service_area,160), category=value(body.primary_category,100), services=value(body.preferred_services,500), exclusions=value(body.exclusions,500), work=value(body.work_type,20), radius=Number(body.service_radius_km);
  if (!name) return failure('name','Enter your name.'); if (!business) return failure('business_name','Enter your business name.');
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return failure('email','Enter a valid email address.');
  if (!/^[+()\d\s-]{8,32}$/.test(phone)) return failure('phone','Enter a valid phone number.');
  if (!area) return failure('service_area','Enter your service area.'); if (![20,30,40,60,100].includes(radius)) return failure('service_radius_km','Choose an available service radius.');
  if (!category || !services || !['residential','commercial','both'].includes(work)) return failure('profile','Complete your Custom Lead Profile.');
  const sms=Boolean(body.sms_addon), categories=Boolean(body.category_addon), [link,total]=LINKS[`${sms?1:0}${categories?1:0}`], id=`ld_${crypto.randomUUID().replaceAll('-','')}`;
  try {
    await env.ONBOARDING_DB.prepare('INSERT INTO onboarding_records (onboarding_id,status,name,business_name,email,phone,service_area,service_radius_km,primary_category,preferred_services,work_type,exclusions,sms_addon,category_addon,additional_categories,monthly_total_aud,stripe_payment_link,source,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)').bind(id,'pending_payment',name,business,email,phone,area,radius,category,services,work,exclusions,sms?1:0,categories?1:0,'[]',total,link,'LeadDrop website signup',new Date().toISOString()).run();
    return Response.json({success:true,onboarding_id:id,stripe_payment_link:link});
  } catch { return Response.json({success:false,message:'We could not save your setup. Please try again.'},{status:500}); }
}
