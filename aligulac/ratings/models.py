from django.contrib.auth.models import User
from django.db import models
from django.db.models import Max, F, Q
from countries import transformations, data

from math import sqrt

class Period(models.Model):
    start = models.DateField('Start date')
    end = models.DateField('End date')
    computed = models.BooleanField(default=False)
    num_retplayers = models.IntegerField('Returning players')
    num_newplayers = models.IntegerField('New players', default=0)
    num_games = models.IntegerField(default=0)
    dom_p = models.FloatField()
    dom_t = models.FloatField()
    dom_z = models.FloatField()

    def __unicode__(self):
        return 'Period #' + str(self.id) + ': ' + str(self.start) + ' to ' + str(self.end)

class Event(models.Model):
    name = models.CharField(max_length=100)
    parent = models.ForeignKey('Event', null=True, blank=True)
    lft = models.IntegerField('Left')
    rgt = models.IntegerField('Right')
    closed = models.BooleanField(default=False)
    big = models.BooleanField(default=False)
    noprint = models.BooleanField(default=False)

    INDIVIDUAL = 'individual'
    TEAM = 'team'
    FREQUENT = 'frequent'
    CATEGORIES = [(INDIVIDUAL, 'Individual'), (TEAM, 'Team'), (FREQUENT, 'Frequent')]
    category = models.CharField(max_length=50, null=True, blank=True, choices=CATEGORIES)

    def __unicode__(self):
        q = ' '.join([e.name for e in\
                Event.objects.filter(lft__lt=self.lft, rgt__gt=self.rgt, noprint=False).order_by('lft')])
        if q != '':
            q += ' '
        q += self.name
        return q

    def get_path(self):
        return Event.objects.filter(lft__lte=self.lft, rgt__gte=self.rgt, noprint=False).order_by('lft')

    def add_child(self, name):
        new = Event(name=name, parent=self)
        if Event.objects.filter(parent=self).exists():
            new.lft = Event.objects.filter(parent=self).aggregate(Max('rgt'))['rgt__max'] + 1
        else:
            new.lft = self.lft + 1
        new.rgt = new.lft + 1
        Event.objects.filter(lft__gt=new.rgt-2).update(lft=F('lft')+2)
        Event.objects.filter(rgt__gt=new.rgt-2).update(rgt=F('rgt')+2)
        new.save()
        return new

    @staticmethod
    def add_root(name):
        new = Event(name=name)
        new.lft = Event.objects.aggregate(Max('rgt'))['rgt__max'] + 1
        new.rgt = new.lft + 1
        new.save()
        return new

    def close(self):
        self.closed = True
        self.save()
        Event.objects.filter(lft__gt=self.lft, lft__lt=self.rgt).update(closed=True)

    def slide(self, shift):
        self.lft += shift
        self.rgt += shift
        self.save()
        for e in Event.objects.filter(parent=self):
            e.slide(shift)

    def reorganize(self, newleft):
        self.lft = newleft

        children = list(Event.objects.filter(parent=self).order_by('lft'))
        nextleft = newleft + 1
        for c in children:
            nextleft = c.reorganize(nextleft) + 1

        self.rgt = nextleft
        self.save()

        return self.rgt

class Player(models.Model):
    class Meta:
        ordering = ['tag']

    tag = models.CharField('In-game name', max_length=30)
    name = models.CharField('Full name', max_length=100, blank=True, null=True)

    countries = []
    for code in data.ccn_to_cca2.values():
        countries.append((code, transformations.cc_to_cn(code)))
    countries.sort(key=lambda a: a[1])
    country = models.CharField('Country', max_length=2, choices=countries, blank=True, null=True)

    birthday = models.DateField(blank=True, null=True)

    P = 'P'
    T = 'T'
    Z = 'Z'
    R = 'R'
    S = 'S'
    RACES = [(P, 'Protoss'), (T, 'Terran'), (Z, 'Zerg'), (R, 'Random'), (S, 'Switcher')]
    race = models.CharField(max_length=1, choices=RACES)

    tlpd_kr_id = models.IntegerField('TLPD Korean ID', blank=True, null=True)
    tlpd_in_id = models.IntegerField('TLPD International ID', blank=True, null=True)
    lp_name = models.CharField('Liquipedia title', blank=True, null=True, max_length=200)
    sc2c_id = models.IntegerField('SC2Charts.net ID', blank=True, null=True)
    sc2e_id = models.IntegerField('SC2Earnings.com ID', blank=True, null=True)

    dom_val = models.FloatField(blank=True, null=True)
    dom_start = models.ForeignKey(Period, blank=True, null=True, related_name='player_dom_start')
    dom_end = models.ForeignKey(Period, blank=True, null=True, related_name='player_dom_end')

    def __unicode__(self):
        if self.country != None and self.country != '':
            return self.tag + ' (' + self.race + ', ' + self.country + ')'
        else:
            return self.tag + ' (' + self.race + ')'

class Team(models.Model):
    name = models.CharField(max_length=100)
    members = models.ManyToManyField(Player, through='TeamMembership')
    scoreak = models.FloatField(default=0.0)
    scorepl = models.FloatField(default=0.0)
    founded = models.DateField(null=True, blank=True)
    disbanded = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)

    def __unicode__(self):
        return self.name

class TeamMembership(models.Model):
    player = models.ForeignKey(Player)
    team = models.ForeignKey(Team)
    start = models.DateField('Date joined', blank=True, null=True)
    end = models.DateField('Date left', blank=True, null=True)
    current = models.BooleanField(default=True, null=False)
    playing = models.BooleanField(default=True, null=False)

class Alias(models.Model):
    name = models.CharField(max_length=100)
    player = models.ForeignKey(Player, null=True)
    team = models.ForeignKey(Team, null=True)

    class Meta:
        verbose_name_plural = 'aliases'

    def __unicode__(self):
        return self.name

class Match(models.Model):
    period = models.ForeignKey(Period)
    date = models.DateField()
    pla = models.ForeignKey(Player, related_name='match_pla', verbose_name='Player A')
    plb = models.ForeignKey(Player, related_name='match_plb', verbose_name='Player B')
    sca = models.SmallIntegerField('Score for player A')
    scb = models.SmallIntegerField('Score for player B')

    P = 'P'
    T = 'T'
    Z = 'Z'
    R = 'R'
    RACES = [(P, 'Protoss'), (T, 'Terran'), (Z, 'Zerg'), (R, 'Random')]
    rca = models.CharField(max_length=1, choices=RACES, null=False, blank=False)
    rcb = models.CharField(max_length=1, choices=RACES, null=False, blank=False)

    treated = models.BooleanField(default=False)
    event = models.CharField(max_length=200, default='', blank=True)
    eventobj = models.ForeignKey(Event, null=True, blank=True)
    submitter = models.ForeignKey(User, null=True, blank=True)

    class Meta:
        verbose_name_plural = 'matches'

    def set_period(self):
        pers = Period.objects.filter(start__lte=self.date).filter(end__gte=self.date)
        self.period = pers[0]

    def __unicode__(self):
        return str(self.date) + ' ' + self.pla.tag + ' ' + str(self.sca) + '-' + str(self.scb) + ' ' + self.plb.tag

class Rating(models.Model):
    period = models.ForeignKey(Period)
    player = models.ForeignKey(Player)

    rating = models.FloatField()
    rating_vp = models.FloatField()
    rating_vt = models.FloatField()
    rating_vz = models.FloatField()

    dev = models.FloatField()
    dev_vp = models.FloatField()
    dev_vt = models.FloatField()
    dev_vz = models.FloatField()

    comp_rat = models.FloatField(null=True, blank=True)
    comp_rat_vp = models.FloatField(null=True, blank=True)
    comp_rat_vt = models.FloatField(null=True, blank=True)
    comp_rat_vz = models.FloatField(null=True, blank=True)

    comp_dev = models.FloatField(null=True, blank=True)
    comp_dev_vp = models.FloatField(null=True, blank=True)
    comp_dev_vt = models.FloatField(null=True, blank=True)
    comp_dev_vz = models.FloatField(null=True, blank=True)

    position = models.IntegerField()
    position_vp = models.IntegerField()
    position_vt = models.IntegerField()
    position_vz = models.IntegerField()

    decay = models.IntegerField(default=0)
    domination = models.FloatField(null=True, blank=True)
    prev = models.ForeignKey('Rating', related_name='prev_rating', null=True, blank=True)

    def ratings(self):
        return [self.rating, self.rating_vp, self.rating_vt, self.rating_vz]

    def devs(self):
        return [self.dev, self.dev_vp, self.dev_vt, self.dev_vz]

    def __unicode__(self):
        return self.player.tag + ' P' + str(self.period.id)

    def get_rating(self, race=None):
        if race == 'P':
            return self.rating_vp
        elif race == 'T':
            return self.rating_vt
        elif race == 'Z':
            return self.rating_vz
        return self.rating

    def get_dev(self, race=None):
        if race == 'P':
            return self.dev_vp
        elif race == 'T':
            return self.dev_vt
        elif race == 'Z':
            return self.dev_vz
        return self.dev

    def get_totalrating(self, race):
        if race in ['P','T','Z']:
            return self.rating + self.get_rating(race)
        else:
            return self.rating

    def get_totaldev(self, race):
        if race in ['P','T','Z']:
            return sqrt(self.get_dev(None)**2 + self.get_dev(race)**2)
        else:
            d = self.get_dev(None)**2
            for r in ['P','T','Z']:
                d += self.get_dev(r)**2/9
            return sqrt(d)

    def set_rating(self, d):
        self.rating = d['M']
        self.rating_vp = d['P']
        self.rating_vt = d['T']
        self.rating_vz = d['Z']

    def set_dev(self, d):
        self.dev = d['M']
        self.dev_vp = d['P']
        self.dev_vt = d['T']
        self.dev_vz = d['Z']
    
    def set_comp_rating(self, d):
        self.comp_rat = d['M']
        self.comp_rat_vp = d['P']
        self.comp_rat_vt = d['T']
        self.comp_rat_vz = d['Z']

    def set_comp_dev(self, d):
        self.comp_dev = d['M']
        self.comp_dev_vp = d['P']
        self.comp_dev_vt = d['T']
        self.comp_dev_vz = d['Z']