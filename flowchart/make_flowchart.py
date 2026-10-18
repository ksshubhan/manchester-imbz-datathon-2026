import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon
BLUE='#0F62FE'; NAVY='#0F2B5B'; GREY='#F2F4F8'; RED='#DA1E28'; AMB='#B28600'; INK='#161616'; MUT='#525252'
fig=plt.figure(figsize=(16,10),dpi=150); ax=fig.add_axes([0,0,1,1]); ax.set_xlim(0,160); ax.set_ylim(0,100); ax.axis('off')
def box(x,y,w,h,title,body='',fc=GREY,tc=INK,ec=None,fs=11):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=0,rounding_size=1.2",fc=fc,ec=ec or fc,lw=1.5))
    ax.text(x+w/2,y+h-2.6,title,ha='center',va='top',fontsize=fs,fontweight='bold',color=tc)
    if body: ax.text(x+w/2,y+h-6.2,body,ha='center',va='top',fontsize=8.6,color=tc if tc!=INK else MUT,linespacing=1.35)
def arrow(x1,y1,x2,y2,label='',lx=0,ly=0,c=MUT):
    ax.annotate('',xy=(x2,y2),xytext=(x1,y1),arrowprops=dict(arrowstyle='-|>',color=c,lw=1.6,mutation_scale=14))
    if label: ax.text((x1+x2)/2+lx,(y1+y2)/2+ly,label,fontsize=9,color=c,ha='center',va='center',fontweight='bold')
def diamond(cx,cy,w,h,text):
    ax.add_patch(Polygon([(cx,cy+h/2),(cx+w/2,cy),(cx,cy-h/2),(cx-w/2,cy)],fc='white',ec=NAVY,lw=1.8))
    ax.text(cx,cy,text,ha='center',va='center',fontsize=9,color=INK,fontweight='bold',linespacing=1.3)

ax.text(3,96.5,"StudentShield: design flowchart",fontsize=18,fontweight='bold',color=INK)
ax.text(3,93,"Everything below runs on IBM LinuxONE (s390x). Top: building the model in Jupyter. Bottom: what happens live when each payment lands.",fontsize=10.5,color=MUT)

# lane 1
ax.add_patch(FancyBboxPatch((2,62),156,28,boxstyle="round,pad=0,rounding_size=1.5",fc='white',ec='#C6C6C6',lw=1.2,ls='--'))
ax.text(4,87.6,"1  BUILD THE MODEL  ·  Jupyter container on LinuxONE (notebooks 01–03)",fontsize=10,fontweight='bold',color=BLUE)
y=65; h=19; w=27
xs=[5,36,67,98,129]
items=[("IBM AML HI-Small","5.08M synthetic payments\n1 in 1,000 laundering\n15 currencies"),
("01 Cleaning","Keep 1–10 Sep\nDrop self-transfers\nConvert amounts to USD"),
("02 Features","25 point-in-time features:\npayment, receiver (fan-in),\nsender (fan-out)"),
("03 Train XGBoost","Train 2–6 Sep (19.0 s, no GPU)\nCut-offs on 7–8 Sep (F2, F0.5)\nTest once on 9–10 Sep"),
("Export","Model + two cut-offs\nto the shared folder\n(~/shared/service_data)")]
for i,(x,(t,b)) in enumerate(zip(xs,items)):
    box(x,y,w,h,t,b,fc=GREY if i<4 else '#E8EEF9')
    if i<4: arrow(x+w+0.3,y+h/2,xs[i+1]-0.3,y+h/2)

# lane 2
ax.add_patch(FancyBboxPatch((2,3),156,56,boxstyle="round,pad=0,rounding_size=1.5",fc='white',ec='#C6C6C6',lw=1.2,ls='--'))
ax.text(4,56.6,"2  SCORE EACH PAYMENT LIVE  ·  Docker containers mule-service + studentshield on a private network",fontsize=10,fontweight='bold',color=BLUE)
ax.plot([142.5,142.5,52,52],[y-0.3,53.5,53.5,52],color=MUT,lw=1.6); arrow(52,52,52,49.4); ax.text(98,54.8,'model + cut-offs loaded when mule-service starts',fontsize=9,color=MUT,ha='center',fontweight='bold')
box(5,34,26,15,"Payment lands","An incoming payment\nto an account",fc=NAVY,tc='white')
box(37,34,30,15,"mule-service /score","25 features → XGBoost score\nunder a millisecond\nTop-3 SHAP reasons",fc=BLUE,tc='white')
arrow(31.3,41.5,36.7,41.5)
diamond(83,41.5,24,15,"Above student\ncut-off?\n(F0.5)")
arrow(67.3,41.5,71,41.5)
diamond(83,15,24,14,"Above analyst\ncut-off?\n(F2)")
arrow(83,34,83,22.2,'no',lx=3)
box(112,36,41,15,"Student warning + analyst alert","Phone asks \"Has someone asked you to move this money?\"\nPayments out are paused · 7 in 10 are real mule activity",fc='#FFF1F1',tc=RED,ec=RED)
arrow(95,41.5,111.7,43,'yes',ly=2)
box(112,17,41,13,"Analyst alert only","Analyst sees account, money flow, reasons, rarity\nStudent's phone stays normal · 1 in 2 are real",fc='#FCF4D6',tc=AMB,ec=AMB)
arrow(95,15,111.7,22,'yes',ly=2)
box(48,5,20,9,"No action","Payment goes through",fc=GREY)
arrow(71,15,68.3,10.5,'no',lx=-3,ly=2)
# student answers loop
box(112,4,41,11,"Student answers → analyst timeline","Re-asked only on new flagged money · after \"Someone\nasked me to move it\" or 3 answers, a specialist takes over",fc='white',ec=NAVY,fs=10)
ax.plot([153.3,156,156],[43.5,43.5,9.5],color=NAVY,lw=1.4,ls='--'); arrow(156,9.5,153.4,9.5,c=NAVY)
box(5,8,40,19,"studentshield web app (port 5000)","The only public container\n/demo  real case, step by step\n/live  full test-day replay\nPhone view + analyst console",fc='#E8EEF9')
arrow(25,27.3,40,33.7,'sends each payment',lx=-9,ly=1,c=MUT)
fig.savefig('StudentShield_flowchart.png'); fig.savefig('StudentShield_flowchart.pdf')
